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
    """Whole-period totals. Cash savings exclude investments; total savings include them."""
    m = monthly_summary(df)
    income, expenses = m["income"].sum(), m["expenses"].sum()
    cash = income - expenses
    invest = -df.loc[df["txn_type"] == "investment", "amount"].sum()

    def rate(x):
        return round(x / income, 4) if income > 0 else None

    return {
        "baseline_income": round(income, 2),
        "total_expenses": round(expenses, 2),            # net of refunds and reimbursements
        "cash_savings": round(cash, 2),
        "investment_contributions": round(invest, 2),
        "total_savings": round(cash + invest, 2),
        "cash_savings_rate": rate(cash),
        "total_savings_rate": rate(cash + invest),
        "one_time_income": round(df.loc[df["one_time"], "amount"].sum(), 2),
        # old names kept so existing code and tests keep working
        "total_income": round(income, 2),
        "net_savings": round(cash, 2),
        "savings_rate": rate(cash),
        "total_investments": round(invest, 2),
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

ESSENTIAL = ["Rent/Housing", "Bills & Utilities", "Groceries", "Healthcare",
             "Transport", "Insurance", "EMI/Loan", "Education"]


def recurring_payments(df, min_months=3, tol=0.10):
    e = df[df["txn_type"] == "expense"].copy()
    e["month"] = _month(e)
    rows = []
    for merchant, g in e.groupby("description_clean"):
        if g["month"].nunique() < min_months:
            continue
        med = g["amount"].median()
        if (g["amount"].sub(med).abs() <= abs(med) * tol).all():
            rows.append({"merchant": merchant, "months": g["month"].nunique(),
                         "typical_amount": round(-med, 2)})
    out = pd.DataFrame(rows, columns=["merchant", "months", "typical_amount"])
    return out.sort_values("typical_amount", ascending=False).reset_index(drop=True)


def find_anomalies(df, min_n=8, k=1.5):
    e = df[df["txn_type"] == "expense"].copy()
    e["spend"] = -e["amount"]
    flagged = []
    for cat, g in e.groupby("category"):
        if len(g) < min_n:
            continue
        q1, q3 = g["spend"].quantile([0.25, 0.75])
        limit = q3 + k * (q3 - q1)
        flagged.append(g[g["spend"] > limit])
    if not flagged:
        return e.iloc[0:0][["date", "description_clean", "category", "spend"]]
    out = pd.concat(flagged)[["date", "description_clean", "category", "spend"]]
    return out.sort_values("spend", ascending=False).reset_index(drop=True)


def essential_split(df, months):
    """Average monthly essential vs discretionary spend over the given months."""
    s = spend_rows(df)
    s = s[s["month"].isin(months)]
    s = s[~s["category"].isin(["Investment/Savings", "Transfer"])]
    ess = s.loc[s["category"].isin(ESSENTIAL), "spend"].sum() / len(months)
    dis = s.loc[~s["category"].isin(ESSENTIAL), "spend"].sum() / len(months)
    return {"essential_monthly": round(ess, 2), "discretionary_monthly": round(dis, 2),
            "emergency_fund_3x": round(3 * ess, 2), "emergency_fund_6x": round(6 * ess, 2)}


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
    print()
    print(recurring_payments(df).to_string())
    print()
    print(find_anomalies(df).head(5).to_string())
    print()
    print(essential_split(df, report["baseline_months"]))