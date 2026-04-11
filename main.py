import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from scraper import scrape_profile, save_session, session_exists
from analyzer import build_prompt

app = FastAPI(title="LinkedIn Outreach Assistant")


@app.get("/api/session")
async def get_session():
    return {"connected": session_exists()}


@app.post("/api/login")
async def login():
    """Open a visible browser so the user can log in to LinkedIn, then save the session."""
    try:
        await save_session()
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/models")
async def get_models():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return {"models": models}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {exc}")


class AnalyzeRequest(BaseModel):
    origin_url: str
    destination_url: str
    model: str


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    async def stream():
        def event(payload: dict) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        try:
            # ── Scrape origin ──────────────────────────────────────────────
            yield event({"type": "status", "message": "Scraping your profile…"})
            origin = await scrape_profile(req.origin_url)
            if origin.get("error"):
                yield event({"type": "status", "message": f"⚠️  {origin['error']}"})

            # ── Scrape destination ─────────────────────────────────────────
            yield event({"type": "status", "message": "Scraping their profile…"})
            dest = await scrape_profile(req.destination_url)
            if dest.get("error"):
                yield event({"type": "status", "message": f"⚠️  {dest['error']}"})

            # Send names back so the UI can show who we found
            yield event({
                "type": "profiles",
                "origin": {
                    "name": origin.get("name") or "Unknown",
                    "headline": origin.get("headline") or "",
                },
                "destination": {
                    "name": dest.get("name") or "Unknown",
                    "headline": dest.get("headline") or "",
                },
            })

            # ── Analyze ────────────────────────────────────────────────────
            yield event({"type": "status", "message": f"Analyzing with {req.model}…"})

            prompt = build_prompt(origin, dest)

            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST",
                    "http://localhost:11434/api/generate",
                    json={
                        "model": req.model,
                        "prompt": prompt,
                        "stream": True,
                        "options": {"temperature": 0.7, "num_predict": 4096},
                    },
                ) as response:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = chunk.get("response", "")
                        if token:
                            yield event({"type": "token", "content": token})
                        if chunk.get("done"):
                            break

            yield event({"type": "done"})

        except Exception as exc:
            yield event({"type": "error", "message": str(exc)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Static files must be mounted last
app.mount("/", StaticFiles(directory="static", html=True), name="static")
