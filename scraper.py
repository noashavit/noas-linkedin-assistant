import os
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SESSION_FILE = os.path.join(os.path.dirname(__file__), "session.json")

_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
]
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_WEBDRIVER_MASK = (
    "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
)

# JS that runs in the browser to extract timestamped posts from the activity feed.
# Uses innerText (rendered, visible text only) — avoids picking up hidden/featured content.
_JS_EXTRACT_POSTS = """
() => {
    const posts = [];
    const seen = new Set();

    document.querySelectorAll('time[datetime]').forEach(timeEl => {
        const datetime = timeEl.getAttribute('datetime') || '';
        const displayTime = (timeEl.innerText || '').trim();

        // Walk up until we find a container that has a realistic post size
        let node = timeEl;
        for (let i = 0; i < 25; i++) {
            node = node.parentElement;
            if (!node) break;
            const text = (node.innerText || '').trim();
            // A real post card: more than 120 chars but not the whole page
            if (text.length > 120 && text.length < 4000) {
                const key = text.slice(0, 120);
                if (!seen.has(key)) {
                    seen.add(key);
                    posts.push({ datetime, displayTime, text });
                }
                break;
            }
        }
    });

    // Sort most-recent first by ISO datetime string (lexicographic works for ISO-8601)
    posts.sort((a, b) => b.datetime.localeCompare(a.datetime));
    return posts.slice(0, 15);
}
"""

# JS that extracts company names from the Experience section.
# LinkedIn renders "Company Name · Employment Type" inside each experience list item.
_JS_EXTRACT_EMPLOYERS = """
() => {
    // Find the Experience section by its heading text
    let expSection = null;
    for (const section of document.querySelectorAll('section')) {
        const h2 = section.querySelector('h2');
        if (h2 && /experience/i.test(h2.innerText)) {
            expSection = section;
            break;
        }
    }
    if (!expSection) return [];

    const employers = [];
    const seen = new Set();

    expSection.querySelectorAll('li').forEach(li => {
        const lines = (li.innerText || '')
            .split('\\n')
            .map(l => l.trim())
            .filter(l => l.length > 0);

        for (const line of lines) {
            // LinkedIn format: "Company Name · Full-time" or "Company Name · 3 yrs"
            if (line.includes('\\u00b7') || line.includes('·')) {
                const sep = line.includes('\\u00b7') ? '\\u00b7' : '·';
                const company = line.split(sep)[0].trim();
                if (
                    company.length > 1 &&
                    company.length < 80 &&
                    !seen.has(company) &&
                    !/^\\d/.test(company) &&
                    !/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/.test(company)
                ) {
                    seen.add(company);
                    employers.push(company);
                }
            }
        }
    });

    return employers;
}
"""


def session_exists() -> bool:
    return os.path.exists(SESSION_FILE)


async def save_session() -> None:
    """Open a visible browser so the user can log in to LinkedIn, then save cookies."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=_LAUNCH_ARGS)
        context = await browser.new_context(user_agent=_USER_AGENT)
        page = await context.new_page()
        await page.goto("https://www.linkedin.com/login")
        await page.wait_for_function(
            """() => {
                const u = window.location.href;
                return u.includes('linkedin.com') &&
                       !u.includes('/login') &&
                       !u.includes('authwall') &&
                       !u.includes('/signup') &&
                       !u.includes('/checkpoint');
            }""",
            timeout=300_000,
        )
        await context.storage_state(path=SESSION_FILE)
        await browser.close()


async def scrape_profile(url: str) -> dict:
    """Scrape a LinkedIn profile page and its recent activity."""
    url = url.rstrip("/").split("?")[0]
    activity_url = f"{url}/recent-activity/all/"

    result = {
        "url": url,
        "name": "",
        "headline": "",
        "meta_description": "",
        "full_text": "",
        "external_links": [],
        "employers": [],
        "recent_activity": "",
        "error": None,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_LAUNCH_ARGS)

        ctx_kwargs = dict(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        if session_exists():
            ctx_kwargs["storage_state"] = SESSION_FILE

        context = await browser.new_context(**ctx_kwargs)
        await context.add_init_script(_WEBDRIVER_MASK)
        page = await context.new_page()

        try:
            # ── Profile page ──────────────────────────────────────────────
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await _scroll(page)

            if _is_auth_wall(page.url):
                result["error"] = (
                    "LinkedIn requires login to view this profile. "
                    "Make sure the profile is public."
                )
                result["name"] = _name_from_url(url)
            else:
                html = await page.content()
                title = await page.title()
                meta = ""
                try:
                    meta = await page.get_attribute('meta[name="description"]', "content") or ""
                except Exception:
                    pass
                result.update(_parse_profile(html, title, meta, url))

                # Extract employers while we're still on the profile page
                try:
                    employers = await page.evaluate(_JS_EXTRACT_EMPLOYERS)
                    if not employers:
                        employers = _extract_employers_from_text(result.get("full_text", ""))
                    result["employers"] = employers
                except Exception:
                    result["employers"] = _extract_employers_from_text(result.get("full_text", ""))

            # ── Activity page ─────────────────────────────────────────────
            await page.goto(activity_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            if _is_auth_wall(page.url):
                result["recent_activity"] = (
                    "Recent activity not accessible — profile may require login."
                )
            else:
                await _scroll_activity(page)

                # Use JS evaluation on the live DOM (innerText = visible text only)
                try:
                    posts = await page.evaluate(_JS_EXTRACT_POSTS)
                except Exception:
                    posts = []

                if posts:
                    result["recent_activity"] = _format_posts(posts)
                else:
                    # Fallback: parse serialised HTML
                    activity_html = await page.content()
                    result["recent_activity"] = _parse_activity_html(activity_html)

        except Exception as exc:
            result["error"] = str(exc)
        finally:
            await browser.close()

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _scroll(page, steps: int = 4) -> None:
    for _ in range(steps):
        await page.keyboard.press("End")
        await page.wait_for_timeout(1100)
    await page.keyboard.press("Home")
    await page.wait_for_timeout(400)


async def _scroll_activity(page, max_steps: int = 10) -> None:
    """Scroll the activity feed until no new content loads."""
    prev_height = 0
    for _ in range(max_steps):
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        prev_height = curr_height
        await page.keyboard.press("End")
        await page.wait_for_timeout(1800)
    await page.keyboard.press("Home")
    await page.wait_for_timeout(400)


def _is_auth_wall(url: str) -> bool:
    return any(k in url for k in ("login", "authwall", "signup", "checkpoint"))


def _name_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    return " ".join(w.capitalize() for w in slug.split("-"))


def _format_posts(posts: list[dict]) -> str:
    """Format JS-extracted posts into a readable string, most-recent first."""
    lines = []
    seen: set[str] = set()
    for post in posts:
        key = post["text"][:120]
        if key in seen:
            continue
        seen.add(key)
        label = post.get("displayTime") or post.get("datetime") or "recent"
        lines.append(f"[{label}]\n{post['text'][:700]}")
    return "\n\n---\n\n".join(lines) if lines else "No recent activity found."


def _extract_employers_from_text(full_text: str) -> list[str]:
    """
    Fallback: parse employer names from the Experience section of the profile text.
    LinkedIn renders each job as 'Company · Employment Type' on a single line.
    """
    exp_match = re.search(
        r"Experience\n(.*?)(?:\n(?:Education|Skills|Licenses|Volunteer|Groups"
        r"|Languages|Recommendations|Accomplishments|Projects)\n|\Z)",
        full_text,
        re.DOTALL,
    )
    if not exp_match:
        return []

    employers: list[str] = []
    seen: set[str] = set()
    for line in exp_match.group(1).split("\n"):
        line = line.strip()
        if "·" in line:
            company = line.split("·")[0].strip()
            if (
                2 < len(company) < 80
                and company not in seen
                and not re.match(r"^\d", company)
                and not re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", company)
            ):
                seen.add(company)
                employers.append(company)
    return employers[:20]


def _parse_profile(html: str, title: str, meta: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    name, headline = "", ""
    clean = title.split(" | ")[0].strip() if " | " in title else title.strip()
    if " - " in clean:
        name, headline = clean.split(" - ", 1)
    else:
        name = clean
    name = name.strip()
    headline = headline.strip()

    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if (
            href.startswith("http")
            and "linkedin.com" not in href
            and "javascript:" not in href
            and len(href) < 200
        ):
            links.append(href)
    links = list(dict.fromkeys(links))[:8]

    full_text = soup.get_text(separator="\n", strip=True)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)

    return {
        "name": name,
        "headline": headline,
        "meta_description": meta,
        "full_text": full_text[:8000],
        "external_links": links,
    }


def _parse_activity_html(html: str) -> str:
    """Fallback HTML parser for activity — used only when JS evaluation fails."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()

    posts: list[tuple[str, str, str]] = []

    for time_el in soup.find_all("time", datetime=True):
        iso_ts = time_el.get("datetime", "")
        display_ts = time_el.get_text(strip=True) or iso_ts
        node = time_el
        for _ in range(20):
            node = node.parent
            if node is None:
                break
            text = re.sub(r"\s+", " ", node.get_text(separator=" ", strip=True))
            if 150 < len(text) < 3000:
                posts.append((iso_ts, display_ts, text))
                break

    if posts:
        posts.sort(key=lambda x: x[0] or "0000-00-00", reverse=True)
        seen: set[str] = set()
        lines: list[str] = []
        for iso_ts, display_ts, text in posts[:12]:
            key = text[:120]
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"[{display_ts or iso_ts}]\n{text[:700]}")
        if lines:
            return "\n\n---\n\n".join(lines)

    raw = soup.get_text(separator="\n", strip=True)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return "(most-recent first)\n\n" + raw[:4000] if raw.strip() else "No recent activity found."
