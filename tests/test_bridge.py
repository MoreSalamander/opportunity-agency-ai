"""Tests for engine/bridge.py — the module the original audit flagged as the
highest-risk code in this repo with zero coverage.

Every fixture DB here is built with a REAL hunter_engine.DataHub (the same
class every Hunter engine actually uses), so these tests exercise bridge.py
against the real on-disk schema, not a hand-rolled stand-in that could drift
from it. The read_ledger bug this audit already fixed — a writable connection
opened via DataHub instead of a real `mode=ro` connection — is exactly the
class of defect `test_read_only_connections_reject_writes` exists to catch
for good.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from hunter_engine.gate import GateEvidence
from hunter_engine.spec import Outcome, OpportunitySpec, Scores, Source, SourceKind, TrustStatus
from hunter_engine.store import DataHub

from engine.bridge import (
    _score_total,
    gather_all,
    read_counts,
    read_ledger,
    read_verified,
)


def _spec(spec_id: str, **overrides: object) -> OpportunitySpec:
    fields: dict[str, object] = {
        "id": spec_id,
        "name": f"Opportunity {spec_id}",
        "type": "generic",
        "sources": [
            Source(url="https://example.com", kind=SourceKind.OFFICIAL, fetched_at="2026-07-01T00:00:00Z")
        ],
        "discovered_by": "test-fixture",
    }
    fields.update(overrides)
    return OpportunitySpec.model_validate(fields)


def _verified(spec_id: str, *, payout_usd_est: float | None = None, scores: Scores | None = None) -> OpportunitySpec:
    spec = _spec(
        spec_id,
        trust_status=TrustStatus.VERIFIED,
        verification=[GateEvidence(check="domain_age", passed=True)],
        gate_version="test-v1",
    )
    if scores is not None:
        spec.scores = scores
    if payout_usd_est is not None:
        spec.outcome = Outcome(payout_usd_est=payout_usd_est, paid=True)
    return spec


@pytest.fixture
def hub_db(tmp_path: Path) -> Path:
    """A real DataHub-created SQLite file with one verified, one rejected,
    and one candidate record, plus a usage_log row — the exact shape bridge.py
    reads from every real Hunter engine repo."""
    db_path = tmp_path / "datahub.sqlite3"
    hub = DataHub(db_path)
    try:
        hub.record_verdict(_verified("v1", payout_usd_est=12.5, scores=Scores(
            reward_potential=30, risk=15, time_efficiency=15, cost=8,
        )))
        hub.record_verdict(_spec(
            "r1", trust_status=TrustStatus.REJECTED,
            verification=[GateEvidence(check="domain_age", passed=False)],
            gate_version="test-v1",
        ))
        hub.save_candidate(_spec("c1"))
        hub._conn.execute(
            "INSERT INTO usage_log (at, agent, model, cost_usd_est)"
            " VALUES ('2026-07-01T00:00:00Z', 'scout', 'llama3', 3.25)"
        )
        hub._conn.commit()
    finally:
        hub.close()
    return db_path


def _repo_dir_for(tmp_path: Path, db_path: Path) -> str:
    """bridge.py derives the DB path from a repo root as repo/data/datahub.sqlite3."""
    repo = tmp_path / "engine_repo"
    (repo / "data").mkdir(parents=True, exist_ok=True)
    db_path.rename(repo / "data" / "datahub.sqlite3")
    return str(repo)


def test_read_only_connections_reject_writes(tmp_path: Path, hub_db: Path) -> None:
    """The core regression test for the bug this audit found: a connection
    opened the way bridge.py opens one must be physically incapable of
    writing, not just documented as read-only."""
    conn = sqlite3.connect(f"file:{hub_db}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly database"):
            conn.execute("INSERT INTO usage_log (at, agent, model) VALUES ('x', 'y', 'z')")
    finally:
        conn.close()


def test_read_ledger_sums_payouts_and_costs(tmp_path: Path, hub_db: Path) -> None:
    repo = _repo_dir_for(tmp_path, hub_db)
    ledger = read_ledger(repo)
    assert ledger == {"earned": 12.5, "spent": 3.25}


def test_read_ledger_missing_db_returns_zeroed_result(tmp_path: Path) -> None:
    ledger = read_ledger(str(tmp_path / "never_ran"))
    assert ledger == {"earned": 0.0, "spent": 0.0}


def test_read_ledger_degrades_on_schema_mismatch(tmp_path: Path) -> None:
    repo = tmp_path / "bad_repo"
    (repo / "data").mkdir(parents=True)
    db_path = repo / "data" / "datahub.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE opportunities (nothing_like_the_real_schema TEXT)")
    conn.commit()
    conn.close()
    ledger = read_ledger(str(repo))
    assert ledger == {"earned": 0.0, "spent": 0.0}


def test_read_counts_reports_all_three_trust_statuses(tmp_path: Path, hub_db: Path) -> None:
    repo = _repo_dir_for(tmp_path, hub_db)
    counts = read_counts(repo)
    assert counts == {"verified": 1, "rejected": 1, "candidates": 1}


def test_read_counts_missing_db_returns_zeroed_result(tmp_path: Path) -> None:
    assert read_counts(str(tmp_path / "never_ran")) == {"verified": 0, "rejected": 0, "candidates": 0}


def test_read_verified_returns_only_verified_records(tmp_path: Path, hub_db: Path) -> None:
    repo = _repo_dir_for(tmp_path, hub_db)
    out = read_verified("crypto_hunter", repo)
    assert len(out) == 1
    assert out[0].opportunity_id == "v1"
    assert out[0].engine == "crypto_hunter"
    assert out[0].score_total == 30 + 15 + 15 + 8


def test_read_verified_missing_db_returns_empty_list(tmp_path: Path) -> None:
    assert read_verified("crypto_hunter", str(tmp_path / "never_ran")) == []


def test_read_verified_skips_malformed_rows_without_failing(tmp_path: Path, hub_db: Path) -> None:
    """A row whose spec_json is missing even the two universally-guaranteed
    fields (id, name) must be skipped, not crash every other engine's read."""
    repo = _repo_dir_for(tmp_path, hub_db)
    db_path = Path(repo) / "data" / "datahub.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO opportunities (id, name, type, trust_status, lifecycle, spec_json)"
        " VALUES ('bad1', 'bad', 'generic', 'verified', 'gated', '{\"not_id_or_name\": true}')"
    )
    conn.commit()
    conn.close()
    out = read_verified("crypto_hunter", repo)
    assert [o.opportunity_id for o in out] == ["v1"]


def test_gather_all_isolates_a_failing_engine(tmp_path: Path, hub_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One engine's read raising must not prevent every other engine's data
    from coming back."""
    good_repo = _repo_dir_for(tmp_path, hub_db)
    engines_config = {
        "good_engine": {"title": "Good", "repo": good_repo, "color": "fff"},
        "broken_engine": {"title": "Broken", "repo": "/nonexistent/broken", "color": "000"},
    }

    import engine.bridge as bridge_mod

    real_read_verified = bridge_mod.read_verified

    def flaky_read_verified(name: str, repo: str) -> list:
        if name == "broken_engine":
            raise RuntimeError("simulated permissions error")
        return real_read_verified(name, repo)

    monkeypatch.setattr(bridge_mod, "read_verified", flaky_read_verified)
    out = gather_all(engines_config)
    assert len(out["good_engine"]) == 1
    assert out["broken_engine"] == []


def test_score_total_computes_the_same_way_hunter_engine_does() -> None:
    scores = {"reward_potential": 30, "risk": 15, "time_efficiency": 15, "cost": 8}
    assert _score_total(scores) == 68


def test_score_total_is_none_for_a_fully_unscored_record() -> None:
    assert _score_total({}) is None


def test_score_total_warns_on_partial_scores(capsys: pytest.CaptureFixture[str]) -> None:
    """A scores dict with SOME but not all four components is schema drift,
    not an ordinary unscored record — the audit's flagged silent-drift case."""
    result = _score_total({"reward_potential": 30}, opportunity_id="drifted-1")
    assert result is None
    captured = capsys.readouterr()
    assert "drifted-1" in captured.out
    assert "schema drift" in captured.out
