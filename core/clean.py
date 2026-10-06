"""Stage 2: combine files and clean transactions."""
from pathlib import Path

import pandas as pd

from core.ingest import load_file


def clean_description(s):
    """Standardize a merchant/narration text."""
    s = s.fillna("").astype(str).str.upper()
    s = s.str.replace(r"^UPI/\d+/", "", regex=True)
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    s = s.str.replace(r"\s+REF\d+$", "", regex=True)
    return s


def load_all(files):
    """files = list of (path, account_type). Returns one combined table."""
    parts = []
    for i, (path, account_type) in enumerate(files):
        t = load_file(path)
        t["account_type"] = account_type
        t["upload"] = i                      # which upload this row came from
        parts.append(t)
    df = pd.concat(parts, ignore_index=True)
    df["description_clean"] = clean_description(df["description"])
    return df

def remove_duplicates(df):
    """Drop overlap/re-upload duplicates, keep legit identical rows. Returns (df, n_removed)."""
    key = ["account_type", "date", "amount", "description_clean"]
    df = df.copy()
    df["occurrence"] = df.groupby(["upload"] + key).cumcount()
    dup = df.duplicated(subset=key + ["occurrence"], keep="first")
    out = df[~dup].drop(columns="occurrence")
    out = out.sort_values("date", kind="stable").reset_index(drop=True)
    return out, int(dup.sum())


if __name__ == "__main__":
    d = Path("data/synthetic")
    df = load_all([(d / "bank_statement.csv", "bank"),
                   (d / "bank_statement.xlsx", "bank"),
                   (d / "card_statement.csv", "card")])
    print("before:", len(df))
    df, removed = remove_duplicates(df)
    print("removed:", removed, "| after:", len(df))
    print("chai rows kept:", (df["description_clean"] == "CHAI POINT").sum())