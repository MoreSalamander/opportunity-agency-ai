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
from typing import Any, TypedDict

from .allocation import BridgedOpportunity


class EngineConfigEntry(TypedDict):
    title: str
    repo: str
    color: str


class CountsDict(TypedDict):
    verified: int
    rejected: int
    candidates: int


def load_engine_config(path: Path) -> dict[str, EngineConfigEntry]:
    with open(path) as f:
        config: dict[str, EngineConfigEntry] = json.load(f)
        return config


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
    except sqlite3.OperationalError as exc:
        # Same schema-mismatch posture as read_ledger/read_counts: a
        # genuinely different table shape from what this bridge expects
        # degrades to "nothing verified" rather than crashing the caller,
        # but says so loudly rather than looking identical to a quiet day.
        print(f"[bridge] schema mismatch reading verified records from {db_path}: {exc}")
        return []
    finally:
        conn.close()

    out: list[BridgedOpportunity] = []
    for spec_json, updated_at in rows:
        spec = json.loads(spec_json)
        try:
            opportunity_id = spec["id"]
            name = spec["name"]
        except KeyError as exc:
            # A row that doesn't even have the two fields every engine's base
            # OpportunitySpec guarantees is malformed beyond this bridge's
            # ability to use it — skip that one record rather than let a
            # single bad row take down every other engine's read.
            print(f"[bridge] skipping a malformed record from {db_path}: missing {exc}")
            continue
        sources = spec.get("sources") or []
        source_url = sources[0]["url"] if sources else None
        scores = spec.get("scores") or {}
        out.append(
            BridgedOpportunity(
                engine=engine,
                opportunity_id=opportunity_id,
                name=name,
                type=spec.get("type", "unknown"),
                summary=spec.get("summary", ""),
                cost_usd_est=spec.get("cost_usd_est"),
                time_minutes_est=spec.get("time_minutes_est"),
                score_total=_score_total(scores, opportunity_id=opportunity_id),
                source_url=source_url,
                gated_at=updated_at,
            )
        )
    return out


def _score_total(scores: dict[str, Any], *, opportunity_id: str = "?") -> int | None:
    """Scores.total is a computed property in hunter_engine, not a stored
    field — recompute it from the four stored components the same way.

    Returns None (deliberately) when any component is missing, exactly as
    hunter_engine's own `Scores.total` property does for an unscored record
    — that is the ordinary, expected "not yet ranked" case and stays silent.
    But if a record has a `scores` dict that isn't simply empty (someone
    started scoring it) and is STILL missing a component, that's the schema-
    drift case the audit flagged: a field rename in a Hunter engine's own
    `Scores` model would silently make every one of its opportunities
    `score_total=None` here with zero indication why. Warn in exactly that
    case, so a real schema mismatch is visible instead of read as "unscored"."""
    parts = [scores.get("reward_potential"), scores.get("risk"),
             scores.get("time_efficiency"), scores.get("cost")]
    if any(p is None for p in parts):
        if scores and not all(p is None for p in parts):
            print(
                f"[bridge] opportunity {opportunity_id}: scores dict has SOME but not "
                f"all four expected components ({scores!r}) — possible schema drift "
                f"in the source engine's Scores model"
            )
        return None
    total = 0
    for p in parts:
        assert p is not None  # the `any(... is None)` check above already ruled this out
        total += int(p)
    return total


def gather_all(
    engines_config: dict[str, EngineConfigEntry]
) -> dict[str, list[BridgedOpportunity]]:
    """Read every configured engine's verified queue. Returns {engine_name: [...]}
    — even engines that returned nothing appear as an empty list, so the
    caller can honestly report "consulted N engines, M had nothing today".

    Each engine is read independently: `read_verified` already degrades
    gracefully for the schema-mismatch case, but this loop also guards
    against anything else going wrong for one specific engine (a permissions
    error, a locked file) so that failure can't take down every OTHER
    engine's read in the same call — the whole point of a per-engine dict
    comprehension is defeated if one raising engine crashes it entirely."""
    out: dict[str, list[BridgedOpportunity]] = {}
    for name, cfg in engines_config.items():
        try:
            out[name] = read_verified(name, cfg["repo"])
        except Exception as exc:
            print(f"[bridge] failed to read verified records for engine {name!r}: {exc}")
            out[name] = []
    return out


def read_ledger(repo: str) -> dict[str, float]:
    """One engine's own earned/spent — read directly, via the same kind of
    real read-only connection `read_verified`/`read_counts` already use.

    This USED to import `hunter_engine.store.DataHub` and call it directly.
    That was a real bug, not just a style choice: `DataHub.__init__` always
    opens a WRITABLE connection and runs `CREATE TABLE IF NOT EXISTS` + a
    commit against whatever path it's given — so every call here executed
    schema DDL and a commit against another engine's live database, despite
    this entire module's docstring promising `mode=ro` throughout. It also
    coupled this repo's own pinned `hunter-engine` version to whichever
    version originally created the target database, with no check anywhere
    that the two agree on schema. Reading the two tables directly avoids
    both problems and needs no dependency on the framework package at all.
    """
    db_path = _datahub_path(repo)
    if not db_path.exists():
        return {"earned": 0.0, "spent": 0.0}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        earned = 0.0
        for (spec_json,) in conn.execute("SELECT spec_json FROM opportunities"):
            try:
                payout = (json.loads(spec_json).get("outcome") or {}).get("payout_usd_est")
                if payout:
                    earned += float(payout)
            except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
                continue  # one malformed row must not corrupt the whole sum
        row = conn.execute("SELECT COALESCE(SUM(cost_usd_est), 0.0) FROM usage_log").fetchone()
        spent = float(row[0]) if row is not None else 0.0
        return {"earned": round(earned, 2), "spent": round(spent, 4)}
    except sqlite3.OperationalError as exc:
        # The database exists but doesn't have the expected tables/columns —
        # a genuine schema mismatch between this repo's assumptions and
        # whatever wrote the target DB, not "nothing recorded yet". Surfaced
        # loudly (unlike the old silent-zero paths this audit flagged
        # elsewhere) so a schema drift is visible instead of read as "$0 earned".
        print(f"[bridge] schema mismatch reading ledger from {db_path}: {exc}")
        return {"earned": 0.0, "spent": 0.0}
    finally:
        conn.close()


def read_counts(repo: str) -> CountsDict:
    """One engine's verified/rejected/candidate counts, for a per-engine
    rollup — same read-only connection, no domain-specific spec needed since
    counting only touches trust_status, not any domain field."""
    db_path = _datahub_path(repo)
    empty: CountsDict = {"verified": 0, "rejected": 0, "candidates": 0}
    if not db_path.exists():
        return empty
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        counts: CountsDict = dict(empty)  # type: ignore[assignment]  # same keys, fresh dict
        for status in ("verified", "rejected", "candidate"):
            row = conn.execute(
                "SELECT COUNT(*) FROM opportunities WHERE trust_status = ?", (status,)
            ).fetchone()
            key = "candidates" if status == "candidate" else status
            counts[key] = row[0]  # type: ignore[literal-required]
        return counts
    except sqlite3.OperationalError as exc:
        # Schema mismatch, same posture as read_ledger: surface a zeroed
        # result rather than a raw exception, but say so loudly.
        print(f"[bridge] schema mismatch reading counts from {db_path}: {exc}")
        return empty
    finally:
        conn.close()
