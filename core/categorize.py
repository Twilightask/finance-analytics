"""Stage 3: rule-based categorization."""
import re
from pathlib import Path

import pandas as pd

RULES_PATH = Path(__file__).parent.parent / "data" / "category_rules.csv"


def load_rules(path=RULES_PATH):
    """Read rules; longest keyword first so specific rules win."""
    rules = pd.read_csv(path)
    rules["keyword"] = rules["keyword"].str.upper().str.strip()
    rules["n"] = rules["keyword"].str.len()
    rules = rules.sort_values("n", ascending=False, kind="stable")
    return rules[["keyword", "category"]]


def categorize(df, rules):
    """Add category and category_source. First matching rule wins."""
    d = df.copy()
    d["category"] = "Other"
    d["category_source"] = "none"
    done = d["unitemized_card"].copy()          # never guess these rows
    for kw, cat in rules.itertuples(index=False):
        hit = ~done & d["description_clean"].str.contains(rf"\b{re.escape(kw)}\b", regex=True)
        d.loc[hit, "category"] = cat
        d.loc[hit, "category_source"] = "rule"
        done = done | hit
    return d


def coverage(df):
    """% of expense rows categorized by a rule."""
    e = df[df["txn_type"] == "expense"]
    return round(100 * (e["category_source"] == "rule").mean(), 1)


if __name__ == "__main__":
    from core.clean import clean_all
    d = Path("data/synthetic")
    df, _ = clean_all([(d / "bank_statement.csv", "bank"),
                       (d / "bank_statement.xlsx", "bank"),
                       (d / "card_statement.csv", "card")])
    df = categorize(df, load_rules())
    print(df.groupby("category")["amount"].agg(["count", "sum"]).round(2).to_string())
    print("coverage:", coverage(df), "%")