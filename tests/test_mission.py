from engine.mission import build_allocation, render_allocation
from tests.conftest import PROFILE, bridged


def test_picks_across_engines_by_score():
    """The core thesis test: opportunities from different domains compete on
    the same footing, in one merged pool, for one shared budget."""
    gathered = {
        "crypto_hunter": [bridged("crypto_hunter", name="Crypto A", score_total=80, time_minutes_est=10)],
        "collectible_hunter": [bridged("collectible_hunter", name="Collectible A", score_total=60, time_minutes_est=10)],
        "free_money_hunter": [],
    }
    record = build_allocation(gathered, PROFILE)
    names = [i.name for i in record.items]
    assert names == ["Crypto A", "Collectible A"]
    assert set(record.engines_consulted) == {"crypto_hunter", "collectible_hunter", "free_money_hunter"}


def test_shared_budget_is_genuinely_shared():
    """Two engines each proposing something that alone fits the budget, but
    together exceed it — only one should make it, proving the budget is
    shared across engines, not per-engine."""
    gathered = {
        "crypto_hunter": [bridged("crypto_hunter", name="Crypto Big", score_total=90, cost_usd_est=80)],
        "collectible_hunter": [bridged("collectible_hunter", name="Collectible Big", score_total=85, cost_usd_est=80)],
    }
    record = build_allocation(gathered, PROFILE)  # budget is $100 total
    assert len(record.items) == 1
    assert record.items[0].name == "Crypto Big"  # higher score wins the shared budget
    assert any("only $" in s.reason for s in record.skipped)


def test_unscored_and_below_floor_are_skipped_honestly():
    gathered = {
        "crypto_hunter": [
            bridged("crypto_hunter", name="Unscored", score_total=None),
            bridged("crypto_hunter", name="Too Low", score_total=5),
        ],
    }
    record = build_allocation(gathered, PROFILE)
    assert record.items == []
    reasons = {s.name: s.reason for s in record.skipped}
    assert reasons["Unscored"] == "not yet scored"
    assert "below floor" in reasons["Too Low"]


def test_empty_engines_produce_an_honest_empty_allocation():
    record = build_allocation({"crypto_hunter": [], "free_money_hunter": []}, PROFILE)
    assert record.items == []
    text = render_allocation(record, {"crypto_hunter": "Crypto Hunter AI"})
    assert "Nothing eligible today across any engine" in text


def test_render_is_deterministic():
    gathered = {"crypto_hunter": [bridged("crypto_hunter", name="X", score_total=50)]}
    a = render_allocation(build_allocation(gathered, PROFILE), {"crypto_hunter": "Crypto Hunter AI"})
    b = render_allocation(build_allocation(gathered, PROFILE), {"crypto_hunter": "Crypto Hunter AI"})
    assert a == b
