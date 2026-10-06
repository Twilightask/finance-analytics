import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import json

from core.categorize import categorize, coverage, load_rules
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