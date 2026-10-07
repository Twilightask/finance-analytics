import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pytest

from core.ingest import load_file, parse_amount, reconcile_balance

DIR = ROOT / "data" / "synthetic"


def test_parse_amount_formats():
    assert parse_amount("-₹18,000.00") == -18000
    assert parse_amount("60,000.00") == 60000
    assert parse_amount("(500)") == -500
    assert parse_amount("1,250.00 Dr") == -1250
    assert pd.isna(parse_amount(""))


def test_row_counts():
    assert len(load_file(DIR / "bank_statement.csv")) == 321
    assert len(load_file(DIR / "bank_statement.xlsx")) == 108   # TOTAL row dropped
    assert len(load_file(DIR / "card_statement.csv")) == 44


def test_card_total_equals_cc_payments():
    card = load_file(DIR / "card_statement.csv")
    assert round(card["amount"].sum(), 2) == -54228.0


def test_bank_balances_reconcile():
    for name in ["bank_statement.csv", "bank_statement.xlsx"]:
        ok, bad_rows = reconcile_balance(load_file(DIR / name))
        assert ok, f"{name} failed at rows {bad_rows}"


def test_no_balance_means_skip():
    ok, _ = reconcile_balance(load_file(DIR / "card_statement.csv"))
    assert ok is None


def test_overlap_adds_up_to_truth():
    csv = load_file(DIR / "bank_statement.csv")
    xl = load_file(DIR / "bank_statement.xlsx")
    truth = pd.read_csv(DIR / "truth_transactions.csv")
    truth_bank = truth[truth.account == "bank"]["amount"].sum()
    overlap = xl.head(5)["amount"].sum()          # first 5 XLSX rows repeat the CSV tail
    assert round(csv["amount"].sum() + xl["amount"].sum() - overlap, 2) == round(truth_bank, 2)


def test_bad_inputs_fail_clearly(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    with pytest.raises(ValueError):
        load_file(empty)
    with pytest.raises(ValueError):
        load_file(tmp_path / "missing.csv")
    pdf = tmp_path / "x.pdf"
    pdf.write_text("hi")
    with pytest.raises(ValueError):
        load_file(pdf)

def test_opening_balance_row_dropped(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("Date,Narration,Amount,Balance\n"
                 "01/07/2026,OPENING BALANCE,0,50000\n"
                 "02/07/2026,SWIGGY,-200,49800\n")
    df = load_file(p)
    assert len(df) == 1 and df["description"].iloc[0] == "SWIGGY"