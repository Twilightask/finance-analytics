import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from core.clean import load_all, remove_duplicates

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