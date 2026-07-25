import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.allocation import BridgedOpportunity  # noqa: E402


def bridged(engine="crypto_hunter", **overrides) -> BridgedOpportunity:
    payload = dict(
        engine=engine,
        opportunity_id=f"opp_{engine}_{overrides.get('name', 'x')}",
        name="Test Opportunity",
        type="test-item",
        summary="",
        cost_usd_est=0.0,
        time_minutes_est=15,
        score_total=50,
        source_url="https://example.org/x",
    )
    payload.update(overrides)
    return BridgedOpportunity(**payload)


PROFILE = {
    "daily_time_minutes": 60,
    "daily_budget_usd": 100,
    "min_total_score": 30,
    "max_allocation_items": 3,
}
