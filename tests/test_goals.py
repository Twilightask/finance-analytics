import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from core.goals import emergency_fund_goal, evaluate_goal, gap_drivers, months_until

TODAY = date(2026, 10, 6)
GOAL = {"name": "Japan Trip", "target_amount": 120000,
        "target_date": "2027-06-06", "already_saved": 20000}


def test_months_until_rounds_up():
    assert months_until("2027-06-06", TODAY) == 8
    assert months_until("2027-06-30", TODAY) == 9
    assert months_until("2026-10-20", TODAY) == 1
    assert months_until("2026-10-06", TODAY) == 0
    assert months_until("2026-09-30", TODAY) == 0


def test_brief_example_is_close():
    r = evaluate_goal(GOAL, 11800, TODAY)
    assert r["remaining"] == 100000 and r["months_left"] == 8
    assert r["required_monthly"] == 12500 and r["gap"] == 700
    assert r["status"] == "close"
    assert r["months_needed_at_current_pace"] == 9      # 100000 / 11800 = 8.47
    assert r["message"].startswith("Based on your recent pattern")


def test_status_thresholds():
    assert evaluate_goal(GOAL, 12500, TODAY)["status"] == "on_track"
    assert evaluate_goal(GOAL, 13000, TODAY)["gap"] == -500       # surplus
    assert evaluate_goal(GOAL, 10000, TODAY)["status"] == "close"  # exactly 80%
    assert evaluate_goal(GOAL, 9000, TODAY)["status"] == "off_track"


def test_goal_already_achieved():
    g = dict(GOAL, already_saved=150000)
    r = evaluate_goal(g, 5000, TODAY)
    assert r["status"] == "achieved" and r["remaining"] == 0


def test_deadline_passed():
    r = evaluate_goal(dict(GOAL, target_date="2026-09-30"), 20000, TODAY)
    assert r["status"] == "deadline_passed" and r["required_monthly"] is None


def test_zero_or_negative_savings():
    for s in (0, -500):
        r = evaluate_goal(GOAL, s, TODAY)
        assert r["status"] == "off_track"
        assert r["months_needed_at_current_pace"] is None


def test_low_confidence_warning():
    assert evaluate_goal(GOAL, 12500, TODAY, low_confidence=True)["warnings"]
    assert evaluate_goal(GOAL, 12500, TODAY)["warnings"] == []


def test_gap_drivers_only_discretionary():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-02", "2026-09-10", "2026-09-12"]),
        "txn_type": ["expense"] * 3, "amount": [-18000.0, -3000.0, -1000.0],
        "category": ["Rent/Housing", "Shopping", "Food"]})
    assert gap_drivers(df, ["2026-09"]) == {"Shopping": 3000.0, "Food": 1000.0}


def test_emergency_fund_goal():
    g = emergency_fund_goal(30000, "2027-12-31", multiple=6)
    assert g["target_amount"] == 180000 and g["name"] == "Emergency Fund"