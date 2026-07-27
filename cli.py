"""Opportunity [Agency AI] — CLI.

  python cli.py gather                  read every engine's verified queue, report counts
  python cli.py allocate                gather -> deterministic cross-engine allocation
  python cli.py day                     allocate, render, save
  python cli.py status                  last allocation summary
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engine.allocation import BridgedOpportunity
from engine.bridge import gather_all, load_engine_config
from engine.mission import build_allocation, render_allocation
from engine.store import OpportunityHub

ROOT = Path(__file__).resolve().parent
ENGINES_PATH = ROOT / "config" / "engines.json"
PROFILE_PATH = ROOT / "config" / "profile.json"
DB_PATH = ROOT / "data" / "datahub.sqlite3"
ALLOCATIONS_DIR = ROOT / "data" / "allocations"


def load_profile() -> dict[str, Any]:
    with open(PROFILE_PATH) as f:
        result: dict[str, Any] = json.load(f)
        return result


def cmd_gather(hub: OpportunityHub) -> dict[str, list[BridgedOpportunity]]:
    engines_config = load_engine_config(ENGINES_PATH)
    gathered = gather_all(engines_config)
    for name, items in gathered.items():
        title = engines_config[name]["title"]
        hub.log_activity("Gatherer", "read verified queue", f"{title}: {len(items)} verified")
        print(f"== {title}: {len(items)} verified opportunities ==")
    return gathered


def cmd_allocate(hub: OpportunityHub) -> None:
    engines_config = load_engine_config(ENGINES_PATH)
    gathered = cmd_gather(hub)
    profile = load_profile()
    record = build_allocation(gathered, profile)
    hub.log_activity(
        "Allocator", "arbitrated priority",
        f"{len(record.items)} picked, {len(record.skipped)} left out",
    )
    hub.save_allocation(record)
    titles = {name: cfg["title"] for name, cfg in engines_config.items()}
    content = render_allocation(record, titles)
    ALLOCATIONS_DIR.mkdir(parents=True, exist_ok=True)
    out = ALLOCATIONS_DIR / f"allocation-{record.date}.md"
    out.write_text(content)
    print()
    print(content)
    print(f"\n[saved to {out}]")


def cmd_status(hub: OpportunityHub) -> None:
    record = hub.latest_allocation()
    if record is None:
        print("no allocation run yet — run `python cli.py day`")
        return
    print(
        f"latest allocation: {record.date} — {len(record.items)} picked, "
        f"{len(record.skipped)} left out, engines: {', '.join(record.engines_consulted)}"
    )


def main() -> None:
    p = argparse.ArgumentParser(prog="opportunity-agency-ai")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gather")
    sub.add_parser("allocate")
    sub.add_parser("day")
    sub.add_parser("status")
    args = p.parse_args()

    hub = OpportunityHub(DB_PATH)
    try:
        if args.cmd == "gather":
            cmd_gather(hub)
        elif args.cmd in ("allocate", "day"):
            cmd_allocate(hub)
        elif args.cmd == "status":
            cmd_status(hub)
    finally:
        hub.close()


if __name__ == "__main__":
    main()
