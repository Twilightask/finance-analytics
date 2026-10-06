import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from core.clean import load_all, remove_duplicates, classify, clean_all

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