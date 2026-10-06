import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import json

from core.categorize import (categorize, coverage, load_rules,
                             load_user_rules, correct_category)
from core.clean import clean_all

DIR = ROOT / "data" / "synthetic"
FILES = [(DIR / "bank_statement.csv", "bank"),
         (DIR / "bank_statement.xlsx", "bank"),
         (DIR / "card_statement.csv", "card")]


def _done():
    df, _ = clean_all(FILES)
    return categorize(df, load_rules())


def test_category_totals_match_truth():
    df = _done()
    spend = df[df["txn_type"].isin(["expense", "refund", "reimbursement"])]
    got = (-spend.groupby("category")["amount"].sum()).round(2).to_dict()
    truth = json.loads((DIR / "ground_truth.json").read_text(encoding="utf-8"))
    assert got == truth["category_expenses_net"]


def test_coverage():
    assert coverage(_done()) == 98.5


def test_whole_word_matching():
    import pandas as pd
    df = pd.DataFrame({"description_clean": ["COLA SHOP", "OLA CABS"],
                       "unitemized_card": [False, False]})
    out = categorize(df, load_rules())
    assert out["category"].tolist() == ["Other", "Transport"]

def test_user_correction_saves_and_applies(tmp_path):
    p = tmp_path / "user_rules.csv"
    df = _done()
    upi = df[(df["category"] == "Other") & df["description_clean"].str.startswith("UPI RAHUL")]
    tid = upi["txn_id"].iloc[0]
    fixed = correct_category(df, tid, "Entertainment", apply_to_merchant=True, path=p)
    assert (fixed.loc[fixed["description_clean"] == "UPI RAHUL SHARMA", "category"] == "Entertainment").all()
    assert (fixed["category_source"] == "user").sum() >= 1
    # rule is remembered for the next upload
    again = categorize(df, load_rules(), load_user_rules(p))
    assert (again.loc[again["description_clean"] == "UPI RAHUL SHARMA", "category_source"] == "user").all()


def test_single_row_override_saves_no_rule(tmp_path):
    p = tmp_path / "user_rules.csv"
    df = _done()
    tid = df.loc[df["description_clean"] == "CHAI POINT", "txn_id"].iloc[0]
    fixed = correct_category(df, tid, "Other", apply_to_merchant=False, path=p)
    assert (fixed["category_source"] == "user").sum() == 1
    assert not p.exists()


def test_user_rule_beats_builtin(tmp_path):
    p = tmp_path / "user_rules.csv"
    df = _done()
    tid = df.loc[df["description_clean"] == "SWIGGY", "txn_id"].iloc[0]
    correct_category(df, tid, "Groceries", apply_to_merchant=True, path=p)
    out = categorize(df, load_rules(), load_user_rules(p))
    assert (out.loc[out["description_clean"] == "SWIGGY", "category"] == "Groceries").all()