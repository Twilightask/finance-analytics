import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pytest

from core.analytics import (baseline, category_spending, month_over_month,
                            monthly_summary, overview, top_merchants,
                            recurring_payments, find_anomalies, essential_split,
                            health_summary, fees_summary, cash_withdrawals,
                            merchant_concentration, income_stability,
                            spending_habits)
from core.categorize import categorize, load_rules
from core.clean import (load_all, remove_duplicates, classify, clean_all,
                        month_coverage, quality_report)
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


def _mini(rows):
    return pd.DataFrame({"date": pd.to_datetime([r[0] for r in rows]),
                         "txn_type": [r[1] for r in rows],
                         "amount": [float(r[2]) for r in rows],
                         "one_time": [r[3] for r in rows]})


def test_reimbursement_nets_expenses_and_is_not_income():
    df = _mini([("2026-01-01", "income", 60000, False),
                ("2026-01-05", "expense", -10000, False),
                ("2026-01-07", "reimbursement", 2000, False)])
    o = overview(df)
    assert o["baseline_income"] == 60000 and o["total_expenses"] == 8000
    assert o["cash_savings"] == 52000


def test_investments_are_savings_not_expenses():
    df = _mini([("2026-01-01", "income", 60000, False),
                ("2026-01-05", "expense", -10000, False),
                ("2026-01-06", "investment", -5000, False),
                ("2026-01-10", "income", 15000, True)])
    o = overview(df)
    assert o["total_expenses"] == 10000 and o["baseline_income"] == 60000
    assert o["cash_savings"] == 50000 and o["investment_contributions"] == 5000
    assert o["total_savings"] == 55000 and o["one_time_income"] == 15000
    assert o["cash_savings_rate"] == round(50000 / 60000, 4)


def test_overview_cash_and_total_match_truth():
    o = overview(_df())
    assert o["cash_savings"] == TRUTH["total_savings"]          # key name is historical
    assert o["total_savings"] == TRUTH["total_savings"] + TRUTH["total_investments"]

def test_reimbursement_keywords():
    df = pd.DataFrame({"description_clean": ["UPI RECEIVED RAHUL", "RAHUL REIMBURSEMENT",
                                             "DINNER SPLIT PRIYA", "RANDOM CREDIT"],
                       "amount": [800.0, 900.0, 1200.0, 500.0]})
    t = classify(df)["txn_type"].tolist()
    assert t == ["reimbursement", "reimbursement", "reimbursement", "review"]


def _rows(rows, cols):
    d = pd.DataFrame(rows, columns=cols)
    d["date"] = pd.to_datetime(d["date"])
    return d


def test_fees_summary():
    df = _rows([("2026-01-05", "expense", -100.0, "Fees & Charges"),
                ("2026-01-09", "expense", -50.0, "Fees & Charges"),
                ("2026-01-10", "expense", -900.0, "Food")],
               ["date", "txn_type", "amount", "category"])
    assert fees_summary(df, ["2026-01"]) == {"total": 150.0, "count": 2}


def test_cash_withdrawals_flagged_when_high():
    df = _rows([("2026-01-05", "expense", -2000.0, "Cash Withdrawal"),
                ("2026-01-06", "expense", -8000.0, "Food")],
               ["date", "txn_type", "amount", "category"])
    c = cash_withdrawals(df, ["2026-01"])
    assert c["monthly_avg"] == 2000 and c["share"] == 0.2 and c["high"] is True


def test_merchant_concentration():
    df = _rows([("2026-01-05", "expense", -600.0, "Food", "SWIGGY"),
                ("2026-01-06", "expense", -200.0, "Food", "SWIGGY"),
                ("2026-01-07", "expense", -200.0, "Food", "ZOMATO"),
                ("2026-01-08", "expense", -18000.0, "Rent/Housing", "LANDLORD")],
               ["date", "txn_type", "amount", "category", "description_clean"])
    r = merchant_concentration(df)
    assert len(r) == 1 and r.loc[0, "merchant"] == "SWIGGY" and r.loc[0, "share_pct"] == 80.0


def test_income_stability_labels():
    def lab(vals):
        df = _rows([(f"2026-0{i + 1}-01", "income", v, False) for i, v in enumerate(vals)],
                   ["date", "txn_type", "amount", "one_time"])
        return income_stability(df, ["2026-01", "2026-02", "2026-03"])["label"]
    assert lab([60000.0, 60000.0, 60000.0]) == "Stable"
    assert lab([60000.0, 45000.0, 60000.0]) == "Variable"
    assert lab([60000.0, 30000.0, 60000.0]) == "Irregular"


def test_spending_habits():
    df = _rows([("2026-01-05", "expense", -100.0),   # Monday
                ("2026-01-10", "expense", -300.0),   # Saturday
                ("2026-01-26", "expense", -50.0)],   # Monday
               ["date", "txn_type", "amount"])
    d, w = spending_habits(df, ["2026-01"])
    assert d["Monday"] == 150 and d["Saturday"] == 300 and d["Tuesday"] == 0
    assert w["Days 1-7"] == 100 and w["Days 8-14"] == 300 and w["Days 22+"] == 50


def test_health_summary_on_demo_data():
    h = health_summary(_df(), 5)
    assert "468 transactions" in h[0][1]
    assert any(l == "ok" and "balance" in t for l, t in h)
    assert not any(l == "warn" for l, _ in h)