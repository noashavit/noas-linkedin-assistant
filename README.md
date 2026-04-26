<img width="160" height="160" alt="noas-icon" src="https://github.com/user-attachments/assets/e71f9c41-a674-4fed-8676-d6704529d2b4" />

# LinkedIn outreach assistant

Scrapes two LinkedIn profiles and generates personalized outreach messages — connection notes and cold emails — written in the sender's authentic voice. Runs entirely on your machine using a local Ollama model. No cloud API calls, no data leaves your computer.

---

## What it does

1. Scrapes the sender's and recipient's LinkedIn profiles (bio, experience, activity feed)
2. Detects shared employers, groups, and recent posts
3. Passes the data to a local LLM (via Ollama)
4. Outputs a structured analysis: tone profile, destination insights, overlap, connection points, outreach strategy
5. Generates 5 LinkedIn connection notes (≤300 chars) and 5 cold email drafts in the sender's voice

See it in action below:

https://github.com/user-attachments/assets/a58e3b8b-206a-4fb8-aa5f-84b9486ff4d6

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| [Ollama](https://ollama.com) | Local LLM inference |
| A LinkedIn account | Scraping requires an active session |
| Chrome / Chromium | Playwright uses it for scraping |

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/your-username/li-insights.git
cd li-insights
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```

### 4. Install and start Ollama

Download Ollama from [ollama.com](https://ollama.com), then pull a model:

```bash
ollama pull gemma3:4b
```

Any model available in Ollama will work. Larger models (8B+) produce noticeably better output and hallucinate less.

### 5. Log in to LinkedIn

Start the app:

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) and click **Connect LinkedIn** in the top-right corner. Log in through the browser window that opens. Your session is saved locally to `session.json` and reused for all future scrapes.

---

## Running the app

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

1. Paste the sender's LinkedIn profile URL (pre-filled automatically if you're logged in)
2. Paste the recipient's LinkedIn profile URL
3. Select a model from the dropdown
4. Click **Analyze**

Results stream in live and are organized into cards: tone analysis, destination insights, overlap, connection points, outreach strategy, LinkedIn drafts, and email drafts.

---

## Project structure

```
li-insights/
├── main.py          # FastAPI server, SSE streaming endpoint
├── scraper.py       # Playwright scraping logic
├── analyzer.py      # Prompt construction
├── requirements.txt
└── static/
    ├── index.html
    ├── app.js
    └── style.css
```

---

## Limitations

- **LinkedIn rate limiting** — LinkedIn may temporarily block scraping if you run too many analyses in quick succession. Space out your requests.
- **Model quality** — Small models (3B–4B) will occasionally hallucinate details. Using a 7B+ model significantly reduces this. The prompt instructs the model to only use facts from the scraped data, but small models don't always comply.
- **LinkedIn DOM changes** — LinkedIn updates its frontend regularly. If scraping breaks (missing employers, empty activity), the CSS selectors in `scraper.py` may need updating.
- **Activity feed depth** — Only the most recent ~10 posts are scraped per profile. Older activity is not included.
- **No public profiles** — Scraping requires an active LinkedIn login. Profiles that block logged-out viewers may return partial data.
- **Local only** — The app is designed to run on localhost. It is not hardened for public deployment (no auth, no rate limiting on the API).
- **macOS/Linux tested** — Windows support is not guaranteed; Playwright and path handling may need adjustments.

---

## Tech stack

- **Backend:** Python, FastAPI, Server-Sent Events (SSE)
- **Scraping:** Playwright (persistent browser session)
- **LLM:** Ollama (local inference, any compatible model)
- **Frontend:** Vanilla JS, no build step required
