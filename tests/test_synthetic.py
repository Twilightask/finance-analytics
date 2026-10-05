import json
from pathlib import Path

import pandas as pd

DIR = Path(__file__).parent.parent / "data" / "synthetic"
truth = json.loads((DIR / "ground_truth.json").read_text(encoding="utf-8"))
truth_df = pd.read_csv(DIR / "truth_transactions.csv")


def test_all_files_exist():
    for name in ["bank_statement.csv", "bank_statement.xlsx", "card_statement.csv",
                 "truth_transactions.csv", "ground_truth.json"]:
        assert (DIR / name).exists(), name


def test_event_count_matches():
    assert len(truth_df) == truth["counts"]["total_events"]
    assert truth["counts"]["bank_rows"] + truth["counts"]["card_rows"] == len(truth_df)


def test_baseline_income_is_salary_only():
    assert truth["total_baseline_income"] == 720000
    assert truth["one_time_income"] == 38000


def test_monthly_totals_add_up():
    m = truth["monthly"]
    assert round(sum(v["income"] for v in m.values()), 2) == truth["total_baseline_income"]
    assert round(sum(v["expenses"] for v in m.values()), 2) == truth["total_expenses_net"]


def test_cc_payments_not_counted_as_expenses():
    card = truth_df[truth_df.account == "card"].amount.sum()
    pay = truth_df[truth_df.txn_type == "cc_payment"].amount.sum()
    assert round(card, 2) == round(pay, 2)
    assert "Transfer" not in truth["category_expenses_net"]


def test_problem_counts():
    c = truth["counts"]
    assert c["cc_payments"] == 12 and c["transfers"] == 4
    assert c["refunds"] == 3 and c["reimbursements"] == 3
    assert c["upi_to_friends"] == 6


def test_bank_files_row_counts():
    csv_rows = len(pd.read_csv(DIR / "bank_statement.csv"))
    xlsx_rows = len(pd.read_excel(DIR / "bank_statement.xlsx", header=3)) - 1  # minus TOTAL row
    assert csv_rows + xlsx_rows - 5 == truth["counts"]["bank_rows"]