import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from core.clean import (load_all, remove_duplicates, classify, clean_all,
                        month_coverage, quality_report)

DIR = ROOT / "data" / "synthetic"
FILES = [(DIR / "bank_statement.csv", "bank"),
         (DIR / "bank_statement.xlsx", "bank"),
         (DIR / "card_statement.csv", "card")]


def test_combined_row_count():
    assert len(load_all(FILES)) == 473          # 468 true + 5 overlap duplicates


def test_cleaned_descriptions_match_truth():
    df = load_all(FILES)
    truth = pd.read_csv(DIR / "truth_transactions.csv")
    assert set(df["description_clean"]) == set(truth["description"].str.upper())

def test_overlap_removed():
    df, removed = remove_duplicates(load_all(FILES))
    assert removed == 5 and len(df) == 468


def test_identical_pairs_survive():
    df, _ = remove_duplicates(load_all(FILES))
    assert (df["description_clean"] == "CHAI POINT").sum() == 6   # 3 pairs x 2


def test_duplicate_upload_ignored():
    csv = DIR / "bank_statement.csv"
    df, removed = remove_duplicates(load_all([(csv, "bank"), (csv, "bank")]))
    assert len(df) == 321 and removed == 321


def test_bank_total_matches_truth():
    df, _ = remove_duplicates(load_all(FILES))
    truth = pd.read_csv(DIR / "truth_transactions.csv")
    got = df[df.account_type == "bank"]["amount"].sum()
    assert round(got, 2) == round(truth[truth.account == "bank"]["amount"].sum(), 2)

def _classified():
    df, _ = remove_duplicates(load_all(FILES))
    return classify(df)


def test_types_match_truth():
    got = _classified().groupby("txn_type")["amount"].agg(["count", "sum"]).round(2)
    truth = pd.read_csv(DIR / "truth_transactions.csv")
    exp = truth.groupby("txn_type")["amount"].agg(["count", "sum"]).round(2)
    pd.testing.assert_frame_equal(got, exp, check_dtype=False)


def test_nothing_needs_review():
    assert not _classified()["needs_review"].any()


def test_one_time_income_flagged():
    df = _classified()
    assert df["one_time"].sum() == 2
    assert df.loc[df.one_time, "amount"].sum() == 38000

def _net_expenses(df):
    return -df.loc[df["txn_type"].isin(["expense", "refund", "reimbursement"]), "amount"].sum()


def test_net_expenses_match_truth():
    df, _ = clean_all(FILES)
    assert round(_net_expenses(df), 2) == 591602


def test_returns_matched_to_right_purchase():
    df, _ = clean_all(FILES)
    by_id = df.set_index("txn_id")
    rets = df[df["txn_type"] == "refund"]
    assert len(rets) == 3 and rets["matched_to"].notna().all()
    for _, r in rets.iterrows():
        assert by_id.loc[r["matched_to"], "description_clean"] == r["description_clean"].removeprefix("REFUND ")
    assert df.loc[df["txn_type"] == "reimbursement", "matched_to"].notna().all()


def test_cc_payments_excluded_when_card_present():
    df, report = clean_all(FILES)
    assert (df["txn_type"] == "cc_payment").sum() == 12
    assert report["unitemized_card_payments"] == 0


def test_bank_only_counts_cc_payments_as_spending():
    df, report = clean_all(FILES[:2])             # no card statement uploaded
    assert report["unitemized_card_payments"] == 12
    assert (df["txn_type"] == "cc_payment").sum() == 0
    assert round(_net_expenses(df), 2) == 591602  # same total, no double counting

def test_all_12_months_complete():
    _, r = clean_all(FILES)
    assert len(r["complete_months"]) == 12 and r["partial_months"] == []


def test_baseline_is_last_6_complete_months():
    _, r = clean_all(FILES)
    assert r["baseline_months"] == ["2026-04", "2026-05", "2026-06",
                                    "2026-07", "2026-08", "2026-09"]


def test_balance_reconciles_after_cleaning():
    _, r = clean_all(FILES)
    assert r["balance_ok"] is True


def test_partial_months_detected():
    df = pd.DataFrame({"date": pd.to_datetime(
        ["2026-01-15", "2026-02-01", "2026-02-27", "2026-03-10"])})
    cov = month_coverage(df).set_index("month")["complete"].to_dict()
    assert cov == {"2026-01": False, "2026-02": True, "2026-03": False}


def test_low_confidence_flag():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-02-28"]),
                       "account_type": ["bank", "bank"],
                       "amount": [100.0, -50.0], "balance": [100.0, 50.0]})
    assert quality_report(df)["low_confidence"] is True

def test_unmatched_reimbursement_not_flagged_but_unmatched_refund_is():
    from core.clean import match_returns
    df = pd.DataFrame({
        "txn_id": [1, 2], "date": pd.to_datetime(["2026-01-10", "2026-01-11"]),
        "description_clean": ["UPI/FRIEND/ROHAN REIMBURSEMENT", "REFUND AMAZON"],
        "amount": [800.0, 500.0], "txn_type": ["reimbursement", "refund"],
        "account_type": ["bank", "bank"], "needs_review": [False, False]})
    out = match_returns(df)
    assert out["needs_review"].tolist() == [False, True]