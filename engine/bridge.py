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
