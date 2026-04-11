def build_prompt(origin: dict, dest: dict) -> str:
    origin_name = origin.get("name") or "the sender"
    dest_name   = dest.get("name") or "the recipient"
    dest_links  = dest.get("external_links") or []
    origin_links = origin.get("external_links") or []

    # ── Shared employer detection ─────────────────────────────────────────
    shared_employer_block = _shared_employer_block(origin, dest)

    def section(label, content, cap=4000):
        return f"{label}:\n{(content or 'Not available')[:cap]}"

    links_line = (
        f"\nExternal links on their profile: {', '.join(dest_links)}"
        if dest_links else ""
    )

    prompt = f"""You are an expert LinkedIn outreach strategist. Analyze these two profiles and produce the output described below.

{shared_employer_block}
LinkedIn outreach rules:
- Lead with a genuine observation or connection point — never a request.
- If {dest_name} posted something recently, reference THAT specifically — it outranks any shared history.
- Mirror {origin_name}'s authentic voice precisely — vocabulary, cadence, formality level.
- LinkedIn notes: 300 characters max.
- Emails: 3-5 sentences, subject line under 60 characters.
- Banned phrases: "I noticed", "I came across", "I hope this finds you well", "touching base", "synergize", "circle back", "leverage", "reaching out".

RECENCY RULE — strictly enforce this ranking when choosing what to reference:
  1. Something {dest_name} posted or engaged with in the last 7 days
  2. Something {dest_name} posted or engaged with in the last 30 days
  3. Shared employer (current) or direct LinkedIn engagement between both users
  4. Shared employer (past), shared education, shared groups
  5. Thematic overlap in their work (weakest — only use if nothing more recent exists)

The activity sections below are timestamped and ordered most-recent-first.
Always prefer the freshest data point you can find.

---

ORIGIN USER — {origin_name} (the person sending the message)
Headline: {origin.get('headline', '')}
Bio: {origin.get('meta_description', '')}
Employers: {', '.join(origin.get('employers', [])) or 'not extracted'}

{section('Profile content', origin.get('full_text'))}

{section('Recent LinkedIn activity (most-recent first)', origin.get('recent_activity'), 2500)}

{('External links: ' + ', '.join(origin_links)) if origin_links else ''}

---

DESTINATION USER — {dest_name} (the person being contacted)
Headline: {dest.get('headline', '')}
Bio: {dest.get('meta_description', '')}
Employers: {', '.join(dest.get('employers', [])) or 'not extracted'}

{section('Profile content', dest.get('full_text'))}

{section('⬇ RECENT ACTIVITY — READ THIS FIRST, most-recent first ⬇', dest.get('recent_activity'), 2500)}
{links_line}

---

Output your response using EXACTLY these section headers (keep the ## prefix):

## TONE ANALYSIS
Describe {origin_name}'s communication style: vocabulary level, sentence structure, formality, distinctive phrases. Quote specific language from their profile or activity if available.

## DESTINATION INSIGHTS
What is {dest_name} focused on RIGHT NOW? Start with the single most recent post or activity item — what was it about, when was it posted, and what does it signal about their current thinking? Then note any persistent themes. Surface external links ({', '.join(dest_links) if dest_links else 'none found'}) and what they reveal.

## CONNECTION POINTS
List overlaps ordered strictly by recency (most recent first). For each, note HOW RECENT it is:
{('- ⚠️  SHARED EMPLOYER(S): ' + ', '.join(_list_shared(origin, dest)) + ' — lead with this') if _list_shared(origin, dest) else ''}
- Very recent posts/activity (days or weeks) — highest priority
- Direct LinkedIn engagement between both users
- Shared employers (past), education, groups
- Thematic alignment (label as background signal only)

## OUTREACH STRATEGY
{"Since they share employer(s) " + ', '.join(_list_shared(origin, dest)) + ", lead the strategy with that." if _list_shared(origin, dest) else ""}
2-3 sentences: the single strongest angle, anchored to the most recent thing {dest_name} posted or engaged with (or the shared employer if one exists). Explain why this specific hook will land right now.

## LINKEDIN DRAFTS

### Draft 1
[message — 300 chars max, mirrors {origin_name}'s voice, most specific/recent hook, uses {dest_name.split()[0]}'s first name]

### Draft 2
[different angle from Draft 1]

### Draft 3
[different angle from Drafts 1–2]

### Draft 4
[different angle from Drafts 1–3]

### Draft 5
[different angle from Drafts 1–4]

## EMAIL DRAFTS

### Draft 1
Subject: [subject line]

[3–5 sentence body, mirrors {origin_name}'s voice, specific connection, uses {dest_name.split()[0]}'s first name]

### Draft 2
Subject: [subject line]

[body]

### Draft 3
Subject: [subject line]

[body]

### Draft 4
Subject: [subject line]

[body]

### Draft 5
Subject: [subject line]

[body]

Write all sections. Use only facts present in the profiles — no invented details."""

    return prompt


def _normalize(name: str) -> str:
    return name.lower().strip()


def _list_shared(origin: dict, dest: dict) -> list[str]:
    """Return origin employer names that also appear in dest's employer list."""
    o_employers = origin.get("employers") or []
    d_employers = dest.get("employers") or []
    d_norm = [_normalize(e) for e in d_employers]

    shared = []
    for oe in o_employers:
        on = _normalize(oe)
        for dn in d_norm:
            # Match if one is a substring of the other (handles Inc./LLC variants)
            if on == dn or (len(on) > 4 and (on in dn or dn in on)):
                shared.append(oe)
                break
    return shared


def _shared_employer_block(origin: dict, dest: dict) -> str:
    shared = _list_shared(origin, dest)
    if not shared:
        return ""
    items = "\n".join(f"  - {e}" for e in shared)
    return f"""⚠️  SHARED EMPLOYERS — mention this prominently in CONNECTION POINTS and lead with it in OUTREACH STRATEGY:
{items}

"""
