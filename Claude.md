# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LinkedIn Outreach Assistant — a tool that scrapes two LinkedIn profiles (origin user = you, destination user = target), analyzes both, and generates personalized outreach messages that mirror the origin user's tone.

## Tech Stack

- **Scraping:** Playwright (headless browser). The user is already logged into LinkedIn in their browser — reuse that session via persistent browser context rather than re-authenticating.
- **AI/LLM:** Local Ollama models (no cloud API calls for analysis).
- **UI:** Web frontend for inputting the two LinkedIn profile URLs.

## Workflow

1. Accept two LinkedIn public profile URLs (origin and destination).
2. Scrape each profile page and `/recent-activity/all/` via Playwright.
3. Extract metadata from `<title>` and `<meta>` tags: name, current employer, past employers, description, skills, groups.
4. Detect co-worker relationships (same employer, current or past) and inject a prominent alert into the analysis prompt. If the users are currently working at the same company outreach should not be about sales or business pushing, but about connecting as people. 
5. Detect cross-engagement: did they like each other's posts, or comment on the same content? Surface this explicitly.
6. Pass all scraped data to a local Ollama model.
7. Output in this order: tone analysis → destination insights → connection points → outreach strategy → 5 LinkedIn drafts → 5 email drafts.

**Recency rule:** Always weight recent connection points and LinkedIn engagement above older shared history.

## Message Quality Rules

- No fluff words or transactional tone.
- Mirror the origin user's authentic voice and style.
- Personal connection (shared interest, experience, or contact) is the most important element — never generic.
- Address destination user by name.
- Keep messages concise.
