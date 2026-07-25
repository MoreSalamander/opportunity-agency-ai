"""Read-only bridges into each Hunter engine's own DataHub.

Same pattern Veritas already uses for crypto-hunter
(veritas/orgs/crypto_hunter/bridge.py): read the engine's SQLite file
directly, read-only (`mode=ro`), never import the engine's code (each has its
own venv and its own domain-specific OpportunitySpec subclass — Opportunity
doesn't need to know those shapes, only the fields every engine's base spec
already carries). Nothing here re-judges anything; each engine's own
deterministic gate already decided trust. Opportunity only reads what
already passed.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .allocation import BridgedOpportunity


def load_engine_config(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _datahub_path(repo: str) -> Path:
    return Path(repo).expanduser() / "data" / "datahub.sqlite3"


def read_verified(engine: str, repo: str) -> list[BridgedOpportunity]:
    """Read every VERIFIED record from one engine's DataHub. Returns an empty
    list (not an error) if the engine has never run — a Hunter engine with
    nothing verified yet is a normal, honest state, not a failure."""
    db_path = _datahub_path(repo)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT spec_json, updated_at FROM opportunities WHERE trust_status = 'verified'"
            " ORDER BY updated_at DESC"
        ).fetchall()
    finally:
        conn.close()

    out: list[BridgedOpportunity] = []
    for spec_json, updated_at in rows:
        spec = json.loads(spec_json)
        sources = spec.get("sources") or []
        source_url = sources[0]["url"] if sources else None
        scores = spec.get("scores") or {}
        out.append(
            BridgedOpportunity(
                engine=engine,
                opportunity_id=spec["id"],
                name=spec["name"],
                type=spec.get("type", "unknown"),
                summary=spec.get("summary", ""),
                cost_usd_est=spec.get("cost_usd_est"),
                time_minutes_est=spec.get("time_minutes_est"),
                score_total=_score_total(scores),
                source_url=source_url,
                gated_at=updated_at,
            )
        )
    return out


def _score_total(scores: dict) -> int | None:
    """Scores.total is a computed property in hunter_engine, not a stored
    field — recompute it from the four stored components the same way."""
    parts = [scores.get("reward_potential"), scores.get("risk"),
             scores.get("time_efficiency"), scores.get("cost")]
    if any(p is None for p in parts):
        return None
    return sum(parts)


def gather_all(engines_config: dict) -> dict[str, list[BridgedOpportunity]]:
    """Read every configured engine's verified queue. Returns {engine_name: [...]}
    — even engines that returned nothing appear as an empty list, so the
    caller can honestly report "consulted N engines, M had nothing today"."""
    return {
        name: read_verified(name, cfg["repo"])
        for name, cfg in engines_config.items()
    }


def read_ledger(repo: str) -> dict:
    """One engine's own earned/spent, via hunter_engine's own DataHub — this
    is shared framework code every engine is built on, not a domain-specific
    import, so reusing it here doesn't break the bridge's isolation the way
    importing a domain's own OpportunitySpec subclass would."""
    from hunter_engine.store import DataHub

    db_path = _datahub_path(repo)
    if not db_path.exists():
        return {"earned": 0.0, "spent": 0.0}
    hub = DataHub(db_path)
    try:
        return {"earned": hub.earned_total(), "spent": hub.usage_totals()["cost_usd_est"]}
    finally:
        hub.close()


def read_counts(repo: str) -> dict:
    """One engine's verified/rejected/candidate counts, for a per-engine
    rollup — same read-only DataHub, no domain-specific spec needed since
    counting only touches trust_status, not any domain field."""
    db_path = _datahub_path(repo)
    if not db_path.exists():
        return {"verified": 0, "rejected": 0, "candidates": 0}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        counts = {}
        for status in ("verified", "rejected", "candidate"):
            row = conn.execute(
                "SELECT COUNT(*) FROM opportunities WHERE trust_status = ?", (status,)
            ).fetchone()
            counts["candidates" if status == "candidate" else status] = row[0]
        return counts
    finally:
        conn.close()
