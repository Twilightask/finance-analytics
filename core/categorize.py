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


def categorize(df, rules, user_rules=None):
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
        if user_rules is not None:
            d = apply_user_rules(d, user_rules)
    return d


USER_RULES_PATH = Path(__file__).parent.parent / "data" / "user_rules.csv"


def load_user_rules(path=USER_RULES_PATH):
    if not Path(path).exists():
        return pd.DataFrame(columns=["description_clean", "category"])
    return pd.read_csv(path)


def apply_user_rules(df, user_rules):
    """Exact-merchant corrections; they beat the built-in keyword rules."""
    d = df.copy()
    mapping = dict(zip(user_rules["description_clean"], user_rules["category"]))
    hit = d["description_clean"].isin(mapping)
    d.loc[hit, "category"] = d.loc[hit, "description_clean"].map(mapping)
    d.loc[hit, "category_source"] = "user"
    return d


def correct_category(df, txn_id, new_category, apply_to_merchant=True,
                     path=USER_RULES_PATH):
    """Change one transaction, or every row of that merchant (and save the rule)."""
    d = df.copy()
    merchant = d.loc[d["txn_id"] == txn_id, "description_clean"].iloc[0]
    if apply_to_merchant:
        rows = d["description_clean"] == merchant
        rules = load_user_rules(path)
        rules = rules[rules["description_clean"] != merchant]
        rules.loc[len(rules)] = [merchant, new_category]
        rules.to_csv(path, index=False)
    else:
        rows = d["txn_id"] == txn_id
    d.loc[rows, "category"] = new_category
    d.loc[rows, "category_source"] = "user"
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