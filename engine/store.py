"""Opportunity's own DataHub-equivalent — same discipline, one level up.

Not an OpportunitySpec store: Opportunity doesn't propose new opportunities,
it arbitrates priority among ones that already exist. The keystone record
here is an AllocationRecord (engine/allocation.py) — one per day, persisted
alongside an activity log so the meta-layer's own agents narrate their work
the same way every Hunter engine's agents do.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .allocation import AllocationRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS allocations (
    date TEXT PRIMARY KEY,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
);
"""


class OpportunityHub:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_allocation(self, record: AllocationRecord) -> None:
        self._conn.execute(
            "INSERT INTO allocations (date, record_json, created_at) VALUES (?, ?, ?)"
            " ON CONFLICT(date) DO UPDATE SET record_json=excluded.record_json",
            (record.date, record.model_dump_json(), datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def latest_allocation(self) -> AllocationRecord | None:
        row = self._conn.execute(
            "SELECT record_json FROM allocations ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return AllocationRecord.model_validate_json(row[0]) if row else None

    def log_activity(self, actor: str, action: str, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO activity_log (at, actor, action, detail) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), actor, action, detail),
        )
        self._conn.commit()

    def activity(self, limit: int = 60) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT at, actor, action, detail FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        keys = ["at", "actor", "action", "detail"]
        return [dict(zip(keys, r)) for r in rows]

    def close(self) -> None:
        self._conn.close()
