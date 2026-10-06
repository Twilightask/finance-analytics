import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pytest

from core.analytics import (baseline, category_spending, month_over_month,
                            monthly_summary, overview, top_merchants,
                            recurring_payments, find_anomalies, essential_split)
from core.categorize import categorize, load_rules
from core.clean import clean_all

DIR = ROOT / "data" / "synthetic"
FILES = [(DIR / "bank_statement.csv", "bank"),
         (DIR / "bank_statement.xlsx", "bank"),
         (DIR / "card_statement.csv", "card")]
TRUTH = json.loads((DIR / "ground_truth.json").read_text(encoding="utf-8"))
BASELINE = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]


def _df():
    df, _ = clean_all(FILES)
    return categorize(df, load_rules())


def test_overview_matches_truth():
    o = overview(_df())
    assert o["total_income"] == TRUTH["total_baseline_income"]
    assert o["total_expenses"] == TRUTH["total_expenses_net"]
    assert o["net_savings"] == TRUTH["total_savings"]
    assert o["total_investments"] == TRUTH["total_investments"]
    assert o["one_time_income"] == TRUTH["one_time_income"]


def test_monthly_matches_truth():
    m = monthly_summary(_df())
    assert len(m) == len(TRUTH["monthly"])
    for month, v in TRUTH["monthly"].items():
        assert m.loc[month, "income"] == pytest.approx(v["income"], abs=0.01)
        assert m.loc[month, "expenses"] == pytest.approx(v["expenses"], abs=0.01)
        assert m.loc[month, "savings"] == pytest.approx(v["savings"], abs=0.01)


def test_category_spending_matches_truth():
    got = category_spending(_df())["spend"].to_dict()
    assert got == pytest.approx(TRUTH["category_expenses_net"], abs=0.01)


def test_baseline_matches_truth():
    b = baseline(_df(), BASELINE)
    exp = [TRUTH["monthly"][m]["expenses"] for m in BASELINE]
    sav = [TRUTH["monthly"][m]["savings"] for m in BASELINE]
    assert b["expenses_mean"] == pytest.approx(sum(exp) / 6, abs=0.01)
    assert b["savings_mean"] == pytest.approx(sum(sav) / 6, abs=0.01)
    assert b["income_mean"] == 60000 and b["income_unstable"] is False


def test_baseline_needs_months():
    with pytest.raises(ValueError):
        baseline(_df(), [])


def test_top_merchant_is_rent():
    t = top_merchants(_df(), 3)
    assert t.index[0] == "RENT TO LANDLORD" and t.iloc[0]["total"] == 216000


def test_month_over_month():
    m = pd.DataFrame({"expenses": [100.0, 150.0, 0.0, 50.0]})
    mom = month_over_month(m)
    assert pd.isna(mom.iloc[0]) and mom.iloc[1] == 50.0
    assert mom.iloc[2] == -100.0 and pd.isna(mom.iloc[3])


def test_month_without_income_has_no_rate():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-05"]), "txn_type": ["expense"],
                       "amount": [-100.0], "one_time": [False]})
    m = monthly_summary(df)
    assert m.loc["2026-01", "expenses"] == 100 and pd.isna(m.loc["2026-01", "savings_rate"])

def test_recurring_finds_fixed_payments():
    r = recurring_payments(_df()).set_index("merchant")
    assert r.loc["RENT TO LANDLORD", "typical_amount"] == 18000
    assert r.loc["RENT TO LANDLORD", "months"] == 12
    assert "AIRTEL BROADBAND" in r.index and "JIO MOBILE RECHARGE" in r.index
    assert "BESCOM ELECTRICITY" not in r.index
    assert "SWIGGY" not in r.index


def test_laptop_is_anomaly():
    a = find_anomalies(_df())
    assert "CROMA LAPTOP" in a["description_clean"].tolist()


def test_anomaly_skips_small_categories():
    a = find_anomalies(_df())
    assert "MAKEMYTRIP GOA TRIP" not in a["description_clean"].tolist()


def test_essential_split_math():
    s = essential_split(_df(), BASELINE)
    assert s["essential_monthly"] >= 19000
    assert s["emergency_fund_3x"] == pytest.approx(3 * s["essential_monthly"], abs=0.01)
    assert s["emergency_fund_6x"] == pytest.approx(6 * s["essential_monthly"], abs=0.01)