"""Opportunity [Agency AI] — read-only dashboard API.

Deliberately read-only: the UI observes the latest allocation. Writes only
happen through `python cli.py day`. Run with `uvicorn app:app --port 8015`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse

from cli import DB_PATH, ENGINES_PATH, load_profile
from engine.bridge import gather_all, load_engine_config, read_counts, read_ledger
from engine.store import OpportunityHub

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

app = FastAPI(title="Opportunity [Agency AI]")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/status")
def status() -> dict[str, Any]:
    """The agency-wide ledger: sum of every engine's own earned/spent. Not
    Opportunity's own spend (it makes no LLM calls yet in v1) — the honest
    question here is whether the WHOLE agency is worth running."""
    hub = OpportunityHub(DB_PATH)
    try:
        record = hub.latest_allocation()
        engines_cfg = load_engine_config(ENGINES_PATH)
        engines = []
        earned = spent = 0.0
        for name, cfg in engines_cfg.items():
            # Per-engine isolation: read_ledger/read_counts already degrade
            # gracefully on their own most-likely failure (schema mismatch),
            # but this still guards the whole endpoint against anything else
            # going wrong for just one engine (a locked file, a permissions
            # error) — without it, one bad engine 500s the dashboard for
            # every other engine too.
            try:
                ledger = read_ledger(cfg["repo"])
                counts = read_counts(cfg["repo"])
            except Exception as exc:
                print(f"[app] failed to read status for engine {name!r}: {exc}")
                ledger = {"earned": 0.0, "spent": 0.0}
                counts = {"verified": 0, "rejected": 0, "candidates": 0}
            earned += ledger["earned"]
            spent += ledger["spent"]
            engines.append({
                "name": name, "title": cfg["title"], "color": cfg.get("color", "8b98a9"),
                "counts": counts, "ledger": ledger,
            })
        return {
            "engines": engines,
            "profile": load_profile(),
            "latest": json.loads(record.model_dump_json()) if record else None,
            "ledger": {"earned": round(earned, 2), "spent": round(spent, 4), "net": round(earned - spent, 2)},
        }
    finally:
        hub.close()


@app.get("/api/scanfield")
def scanfield() -> dict[str, Any]:
    """The agency's coverage as a graph: Opportunity at the center, each
    Hunter engine as its own node (in its own brand color), and every
    verified opportunity across every engine on the outer shell — the ones
    that made today's allocation lit brighter than the ones that didn't."""
    hub = OpportunityHub(DB_PATH)
    try:
        engines_cfg = load_engine_config(ENGINES_PATH)
        record = hub.latest_allocation()
        picked_ids = {(i.engine, i.opportunity_id) for i in record.items} if record else set()

        agents = [
            {"name": cfg["title"], "active": True, "color": cfg.get("color", "8b98a9")}
            for cfg in engines_cfg.values()
        ]
        gathered = gather_all(engines_cfg)
        sources = []
        for engine_name, items in gathered.items():
            color = engines_cfg[engine_name].get("color", "8b98a9")
            for o in items:
                sources.append({
                    "name": o.name,
                    "flagged": (engine_name, o.opportunity_id) in picked_ids,
                    "color": color,
                })
        return {"gate": "Opportunity", "agents": agents, "sources": sources}
    finally:
        hub.close()


@app.get("/api/tonight")
def tonight() -> dict[str, Any]:
    """Today's allocation as structured data — the cross-engine equivalent
    of a single engine's own Tonight's Orders."""
    hub = OpportunityHub(DB_PATH)
    try:
        engines_cfg = load_engine_config(ENGINES_PATH)
        titles = {n: c["title"] for n, c in engines_cfg.items()}
        record = hub.latest_allocation()
        if record is None:
            return {"items": [], "time_used": 0, "time_budget": 0, "money_used": 0, "money_budget": 0}
        items = [
            {
                "name": i.name,
                "type": i.type,
                "sub": titles.get(i.engine, i.engine),
                "minutes": i.time_minutes_est,
                "cost": i.cost_usd_est,
                "score": i.score_total,
                "plain": f"From {titles.get(i.engine, i.engine)} — already passed its own gate; this allocation only decided priority.",
                "source": i.source_url,
            }
            for i in record.items
        ]
        return {
            "items": items,
            "time_used": record.time_used_minutes,
            "time_budget": record.time_budget_minutes,
            "money_used": record.money_used_usd,
            "money_budget": record.money_budget_usd,
        }
    finally:
        hub.close()


@app.get("/api/leads")
def leads() -> list[dict[str, Any]]:
    """Every verified opportunity across every engine — the cross-engine
    equivalent of a single engine's own "every lead" list. All of these
    already passed their own engine's gate; what's shown here is only
    whether today's allocation picked them."""
    hub = OpportunityHub(DB_PATH)
    try:
        engines_cfg = load_engine_config(ENGINES_PATH)
        titles = {n: c["title"] for n, c in engines_cfg.items()}
        record = hub.latest_allocation()
        picked_ids = {(i.engine, i.opportunity_id) for i in record.items} if record else set()
        gathered = gather_all(engines_cfg)
        out = []
        for engine_name, items in gathered.items():
            for o in items:
                out.append({
                    "name": o.name,
                    "engine": titles.get(engine_name, engine_name),
                    "type": o.type,
                    "score": o.score_total,
                    "time_minutes_est": o.time_minutes_est,
                    "cost_usd_est": o.cost_usd_est,
                    "picked": (engine_name, o.opportunity_id) in picked_ids,
                })
        return out
    finally:
        hub.close()


@app.get("/api/skipped")
def skipped() -> list[dict[str, Any]]:
    """Today's left-out items and why — the cross-engine equivalent of a
    single engine's rejected list, except nothing here failed a gate; it
    lost on priority against the shared budget."""
    hub = OpportunityHub(DB_PATH)
    try:
        engines_cfg = load_engine_config(ENGINES_PATH)
        titles = {n: c["title"] for n, c in engines_cfg.items()}
        record = hub.latest_allocation()
        if record is None:
            return []
        return [
            {"name": s.name, "engine": titles.get(s.engine, s.engine), "reason": s.reason}
            for s in record.skipped
        ]
    finally:
        hub.close()
