import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from core.categorize import categorize, load_rules
from core.clean import clean_all
from core.db import load_goal, load_transactions, save_goal, save_transactions

DIR = ROOT / "data" / "synthetic"
FILES = [(DIR / "bank_statement.csv", "bank"),
         (DIR / "bank_statement.xlsx", "bank"),
         (DIR / "card_statement.csv", "card")]


def test_round_trip_is_identical(tmp_path):
    p = tmp_path / "t.db"
    df, _ = clean_all(FILES)
    df = categorize(df, load_rules())
    save_transactions(df, p)
    back = load_transactions(p)
    assert list(back.columns) == list(df.columns)
    pd.testing.assert_frame_equal(back, df, check_dtype=False)


def test_nothing_saved_returns_none(tmp_path):
    p = tmp_path / "empty.db"
    assert load_transactions(p) is None
    assert load_goal(p) is None


def test_only_one_active_goal(tmp_path):
    p = tmp_path / "g.db"
    save_goal({"name": "Japan Trip", "target_amount": 120000,
               "target_date": "2027-06-30", "already_saved": 20000}, p)
    save_goal({"name": "Emergency Fund", "target_amount": 300000,
               "target_date": "2027-12-31", "already_saved": 0}, p)
    g = load_goal(p)
    assert g["name"] == "Emergency Fund" and g["target_amount"] == 300000