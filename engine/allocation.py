"""The allocation record — Opportunity's own keystone, one level up from
`OpportunitySpec`.

A Hunter engine's gate already decided TRUTH for each of its own records —
Opportunity never re-judges that. What Opportunity decides is PRIORITY:
given one shared budget of time and money, which of today's independently-
verified opportunities — sourced from any number of different domains —
actually get today's allocation, and which get honestly left out.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class BridgedOpportunity(BaseModel):
    """A read-only snapshot of one VERIFIED record from a Hunter engine's own
    DataHub. Not re-validated, not re-gated — Opportunity trusts the engine's
    own deterministic gate verdict completely. Only used to arbitrate
    priority, never truth."""

    engine: str  # e.g. "crypto_hunter", "collectible_hunter", "free_money_hunter"
    opportunity_id: str  # the engine's own spec.id
    name: str
    type: str
    summary: str = ""
    cost_usd_est: Optional[float] = None
    time_minutes_est: Optional[int] = None
    score_total: Optional[int] = None
    source_url: Optional[str] = None
    gated_at: Optional[str] = None


class AllocationItem(BaseModel):
    """One opportunity that made today's cross-engine allocation."""

    engine: str
    opportunity_id: str
    name: str
    type: str
    cost_usd_est: float
    time_minutes_est: int
    score_total: Optional[int] = None
    source_url: Optional[str] = None


class SkippedItem(BaseModel):
    engine: str
    name: str
    reason: str


class AllocationRecord(BaseModel):
    """The day's decision: deterministic, reproducible from the same inputs.
    This is the record type Opportunity's own DataHub persists — not an
    OpportunitySpec, since Opportunity isn't proposing new opportunities, it's
    arbitrating priority among opportunities that already exist."""

    date: str = Field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    engines_consulted: list[str] = Field(default_factory=list)
    items: list[AllocationItem] = Field(default_factory=list)
    skipped: list[SkippedItem] = Field(default_factory=list)
    time_budget_minutes: int = 0
    money_budget_usd: float = 0.0
    time_used_minutes: int = 0
    money_used_usd: float = 0.0
    strategy_note: Optional[str] = None
