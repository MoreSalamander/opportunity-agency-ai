"""Opportunity [Agency AI] — read-only dashboard API.

Deliberately read-only: the UI observes the latest allocation. Writes only
happen through `python cli.py day`. Run with `uvicorn app:app --port 8015`.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from cli import DB_PATH, ENGINES_PATH, load_profile
from engine.bridge import load_engine_config
from engine.store import OpportunityHub

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

app = FastAPI(title="Opportunity [Agency AI]")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/status")
def status():
    hub = OpportunityHub(DB_PATH)
    try:
        record = hub.latest_allocation()
        engines = load_engine_config(ENGINES_PATH)
        return {
            "engines": [{"name": n, "title": c["title"]} for n, c in engines.items()],
            "profile": load_profile(),
            "latest": json.loads(record.model_dump_json()) if record else None,
            "feed": hub.activity(60),
        }
    finally:
        hub.close()
