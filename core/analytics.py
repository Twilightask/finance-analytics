"""Stage 5: analytics engine. All numbers come from here; the UI only displays them."""
import numpy as np
import pandas as pd

SPEND_TYPES = ["expense", "refund", "reimbursement"]


def _month(df):
    return df["date"].dt.strftime("%Y-%m")


def spend_rows(df):
    """Spending rows with a positive 'spend' column (refunds come out negative)."""
    s = df[df["txn_type"].isin(SPEND_TYPES)].copy()
    s["month"] = _month(s)
    s["spend"] = -s["amount"]
    return s


def income_rows(df):
    """Regular income only. One-time income (bonus, tax refund) is excluded."""
    i = df[(df["txn_type"] == "income") & ~df["one_time"]].copy()
    i["month"] = _month(i)
    return i


def monthly_summary(df):
    """One row per month: income, expenses, savings, savings_rate."""
    months = [str(p) for p in pd.period_range(df["date"].min(), df["date"].max(), freq="M")]
    inc = income_rows(df).groupby("month")["amount"].sum()
    exp = spend_rows(df).groupby("month")["spend"].sum()
    out = pd.DataFrame({"income": inc, "expenses": exp}).reindex(months).fillna(0.0)
    out["savings"] = out["income"] - out["expenses"]
    out["savings_rate"] = (out["savings"] / out["income"]).where(out["income"] > 0).round(4)
    out[["income", "expenses", "savings"]] = out[["income", "expenses", "savings"]].round(2)
    out.index.name = "month"
    return out


def overview(df):
    """Whole-period totals."""
    m = monthly_summary(df)
    income, expenses = m["income"].sum(), m["expenses"].sum()
    return {
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "net_savings": round(income - expenses, 2),
        "savings_rate": round((income - expenses) / income, 4) if income > 0 else None,
        "total_investments": round(-df.loc[df["txn_type"] == "investment", "amount"].sum(), 2),
        "one_time_income": round(df.loc[df["one_time"], "amount"].sum(), 2),
    }


def baseline(df, months, gap_warn=0.20, cv_warn=0.20):
    """Mean and median monthly figures over the baseline months, plus warnings."""
    if not months:
        raise ValueError("No complete months available for a baseline.")
    m = monthly_summary(df).loc[months]
    out = {"months": list(months)}
    for col in ["income", "expenses", "savings"]:
        out[f"{col}_mean"] = round(float(m[col].mean()), 2)
        out[f"{col}_median"] = round(float(m[col].median()), 2)
    mean_s, med_s = out["savings_mean"], out["savings_median"]
    out["savings_skewed"] = bool(mean_s != 0 and abs(mean_s - med_s) / abs(mean_s) > gap_warn)
    inc_mean = m["income"].mean()
    out["income_unstable"] = bool(inc_mean > 0 and m["income"].std(ddof=0) / inc_mean > cv_warn)
    return out


def category_spending(df, months=None):
    """Net spend per category and its share of total spending."""
    s = spend_rows(df)
    if months is not None:
        s = s[s["month"].isin(months)]
    c = s.groupby("category")["spend"].sum().sort_values(ascending=False)
    out = pd.DataFrame({"spend": c.round(2)})
    out["share_pct"] = (100 * c / c.sum()).round(1)
    return out


def top_merchants(df, n=10):
    e = df[df["txn_type"] == "expense"]
    g = e.groupby("description_clean")["amount"].agg(total="sum", count="count")
    g["total"] = -g["total"]
    return g.sort_values("total", ascending=False).head(n).round(2)


def month_over_month(monthly):
    """% change in expenses vs the previous month (NaN when the previous month is 0)."""
    change = monthly["expenses"].pct_change(fill_method=None) * 100
    return change.replace([np.inf, -np.inf], np.nan).round(1)


if __name__ == "__main__":
    from pathlib import Path

    from core.categorize import categorize, load_rules
    from core.clean import clean_all

    d = Path("data/synthetic")
    df, report = clean_all([(d / "bank_statement.csv", "bank"),
                            (d / "bank_statement.xlsx", "bank"),
                            (d / "card_statement.csv", "card")])
    df = categorize(df, load_rules())
    for k, v in overview(df).items():
        print(f"{k}: {v}")
    print()
    b = baseline(df, report["baseline_months"])
    for k, v in b.items():
        print(f"{k}: {v}")
    print()
    print(category_spending(df).head(5).to_string())
    print()
    print(top_merchants(df, 3).to_string())