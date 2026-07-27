"""Cross-engine arbitration — the "weigh" step.

Generalizes hunter_engine.mission.build_mission from "one engine's verified
candidates against one budget" to "N engines' verified candidates against ONE
shared budget." Each engine's gate already settled truth; this settles
priority — deterministically, the same discipline every Hunter engine's own
mission-builder already uses: greedy by score within caps, an honest
left-out list, reproducible from the same inputs.
"""

from __future__ import annotations

from typing import Any

from .allocation import AllocationItem, AllocationRecord, BridgedOpportunity, SkippedItem


def build_allocation(
    gathered: dict[str, list[BridgedOpportunity]], profile: dict[str, Any]
) -> AllocationRecord:
    """Deterministic cross-engine allocation. Greedy by score_total within a
    single shared time/money budget — the same algorithm every individual
    engine's own mission.py uses, just pointed at a merged, engine-tagged pool
    instead of one engine's own queue."""
    score_floor = int(profile.get("min_total_score", 0))
    time_cap = int(profile["daily_time_minutes"])
    money_cap = float(profile["daily_budget_usd"])
    max_items = int(profile.get("max_allocation_items", 5))

    pool: list[BridgedOpportunity] = [o for items in gathered.values() for o in items]
    pool.sort(key=lambda o: (o.score_total is None, -(o.score_total or 0)))

    record = AllocationRecord(
        engines_consulted=sorted(gathered.keys()),
        time_budget_minutes=time_cap,
        money_budget_usd=money_cap,
    )

    for o in pool:
        if o.score_total is None:
            record.skipped.append(SkippedItem(engine=o.engine, name=o.name, reason="not yet scored"))
            continue
        if o.score_total < score_floor:
            record.skipped.append(
                SkippedItem(engine=o.engine, name=o.name,
                            reason=f"score {o.score_total} below floor {score_floor}")
            )
            continue
        cost = o.cost_usd_est or 0.0
        minutes = o.time_minutes_est if o.time_minutes_est is not None else 30
        if len(record.items) >= max_items:
            record.skipped.append(SkippedItem(engine=o.engine, name=o.name, reason="allocation is full"))
            continue
        if record.time_used_minutes + minutes > time_cap:
            record.skipped.append(
                SkippedItem(engine=o.engine, name=o.name,
                            reason=f"needs ~{minutes} min; only {time_cap - record.time_used_minutes} left")
            )
            continue
        if record.money_used_usd + cost > money_cap:
            record.skipped.append(
                SkippedItem(engine=o.engine, name=o.name,
                            reason=f"needs ~${cost:g}; only ${money_cap - record.money_used_usd:g} left")
            )
            continue
        record.items.append(
            AllocationItem(
                engine=o.engine, opportunity_id=o.opportunity_id, name=o.name, type=o.type,
                cost_usd_est=cost, time_minutes_est=minutes, score_total=o.score_total,
                source_url=o.source_url,
            )
        )
        record.time_used_minutes += minutes
        record.money_used_usd += cost

    return record


def render_allocation(record: AllocationRecord, engine_titles: dict[str, str]) -> str:
    """Deterministic markdown — the source of truth any future voicing layer
    may only restate, never alter."""
    lines = [
        f"# Opportunity [Agency AI] — Today's Allocation ({record.date})",
        "",
        f"**Consulted {len(record.engines_consulted)} engines: "
        + ", ".join(engine_titles.get(e, e) for e in record.engines_consulted) + "**",
        "",
        f"**Time: ~{record.time_used_minutes} of {record.time_budget_minutes} min · "
        f"Budget: ${record.money_used_usd:g} of ${record.money_budget_usd:g}**",
        "",
    ]
    if not record.items:
        lines.append("_Nothing eligible today across any engine — that is the system working._")
    for i, item in enumerate(record.items, 1):
        title = engine_titles.get(item.engine, item.engine)
        lines.append(
            f"{i}. **{item.name}** ({item.type}) — from *{title}* — "
            f"score {item.score_total}/90 · ~{item.time_minutes_est} min · ${item.cost_usd_est:g}"
        )
        if item.source_url:
            lines.append(f"   - Verify at source: {item.source_url}")
    if record.skipped:
        lines.append("")
        lines.append("**Left out (and why):**")
        for s in record.skipped:
            title = engine_titles.get(s.engine, s.engine)
            lines.append(f"- {s.name} ({title}) — {s.reason}")
    if record.strategy_note:
        lines.append("")
        lines.append(f"**Strategy note:** {record.strategy_note}")
    lines.append("")
    lines.append(
        "_Every item here already passed its own engine's deterministic gate. "
        "This allocation only decided priority — one shared budget, competing "
        "legitimate claims on it. Opportunity never holds keys, executes "
        "transactions, or files anything on your behalf._"
    )
    return "\n".join(lines)
