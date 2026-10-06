"""Stage 2: combine files and clean transactions."""
from pathlib import Path

import pandas as pd
import numpy as np

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

def classify(df):
    """Add txn_type, one_time and needs_review columns."""
    d = df.copy()
    s = d["description_clean"]
    pos = d["amount"] > 0
    neg = d["amount"] < 0
    conditions = [
        pos & s.str.contains(r"SALARY|BONUS|TAX REFUND"),
        pos & s.str.startswith("REFUND "),
        pos & s.str.startswith("UPI RECEIVED"),
        neg & s.str.contains("CREDIT CARD BILL"),
        neg & s.str.contains(r"^(?:SIP|RD|PPF|FD)\b|MUTUAL FUND|ZERODHA|BROKERAGE"),
        neg & s.str.contains("TRANSFER TO OWN"),
        neg,
    ]
    choices = ["income", "refund", "reimbursement", "cc_payment",
               "investment", "transfer", "expense"]
    d["txn_type"] = np.select(conditions, choices, default="review")
    d["one_time"] = pos & s.str.contains(r"BONUS|TAX REFUND")
    d["needs_review"] = d["txn_type"] == "review"
    return d

def apply_card_rule(df):
    """Exclude card bill payments only if that month has card transactions."""
    d = df.copy()
    month = d["date"].dt.to_period("M")
    card_months = set(month[d["account_type"] == "card"])
    unitemized = (d["txn_type"] == "cc_payment") & ~month.isin(card_months)
    d.loc[unitemized, "txn_type"] = "expense"      # only record of that spending
    d["unitemized_card"] = unitemized
    return d


def match_returns(df, max_days=30):
    """Link each refund/reimbursement to the earlier expense it offsets."""
    d = df.copy()
    d["matched_to"] = np.nan
    used = set()
    for i in d.index[d["txn_type"].isin(["refund", "reimbursement"])]:
        row = d.loc[i]
        if row["txn_type"] == "refund":
            original = row["description_clean"].removeprefix("REFUND ")
        else:
            original = "UPI " + row["description_clean"].removeprefix("UPI RECEIVED ")
        cand = d[(d["txn_type"] == "expense")
                 & (d["description_clean"] == original)
                 & (d["account_type"] == row["account_type"])
                 & (d["date"] <= row["date"])
                 & (d["date"] >= row["date"] - pd.Timedelta(days=max_days))
                 & ~d["txn_id"].isin(used)]
        if row["txn_type"] == "refund":
            cand = cand[cand["amount"] == -row["amount"]]       # exact amount
        else:
            cand = cand[cand["amount"] <= -row["amount"]]       # partial repayment ok
        if len(cand):
            j = cand["txn_id"].iloc[-1]                          # most recent purchase
            d.loc[i, "matched_to"] = j
            used.add(j)
    unmatched = d["txn_type"].isin(["refund", "reimbursement"]) & d["matched_to"].isna()
    d["needs_review"] = d["needs_review"] | unmatched
    return d


def clean_all(files):
    """Full cleaning pipeline. Returns (clean table, report dict)."""
    df, removed = remove_duplicates(load_all(files))
    df = classify(df)
    df.insert(0, "txn_id", range(1, len(df) + 1))
    df = match_returns(apply_card_rule(df))
    report = {"duplicates_removed": removed,
              "unitemized_card_payments": int(df["unitemized_card"].sum()),
              "needs_review": int(df["needs_review"].sum())}
    return df, report

if __name__ == "__main__":
    d = Path("data/synthetic")
    df, report = clean_all([(d / "bank_statement.csv", "bank"),
                            (d / "bank_statement.xlsx", "bank"),
                            (d / "card_statement.csv", "card")])
    print(df.groupby("txn_type")["amount"].agg(["count", "sum"]).round(2).to_string())
    print("matched returns:", int(df["matched_to"].notna().sum()), "of 6")
    print(report)
    net = -df.loc[df["txn_type"].isin(["expense", "refund", "reimbursement"]), "amount"].sum()
    print("net expenses:", round(net, 2))