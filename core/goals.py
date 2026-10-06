"""Stage 6: goal engine and what-if simulator (deterministic, no LLM)."""
import math
from datetime import date

import pandas as pd

from core.analytics import ESSENTIAL, category_spending

NOT_SPENDING = ["Investment/Savings", "Transfer"]


def _to_date(x):
    return pd.Timestamp(x).date()


def months_until(target_date, today):
    """Calendar months to the deadline, rounded up (min 1). 0 if already passed."""
    t, n = _to_date(target_date), _to_date(today)
    if t <= n:
        return 0
    months = (t.year - n.year) * 12 + (t.month - n.month)
    if t.day > n.day:
        months += 1
    return max(months, 1)


def evaluate_goal(goal, monthly_savings, today=None, low_confidence=False):
    """goal = dict(name, target_amount, target_date, already_saved)."""
    today = _to_date(today or date.today())
    target = float(goal["target_amount"])
    saved = float(goal.get("already_saved") or 0)
    current = float(monthly_savings)
    remaining = round(max(target - saved, 0), 2)
    out = {"goal": goal["name"], "remaining": remaining,
           "current_monthly_saving": round(current, 2), "months_left": None,
           "required_monthly": None, "gap": None, "ratio": None,
           "months_needed_at_current_pace": None, "status": None,
           "message": None, "warnings": []}
    if low_confidence:
        out["warnings"].append("Fewer than 3 complete months of data: treat this "
                               "result as low confidence.")

    if remaining == 0:
        out["status"] = "achieved"
        out["message"] = "You have already reached this target."
        return out

    months = months_until(goal["target_date"], today)
    out["months_left"] = months
    if months == 0:
        out["status"] = "deadline_passed"
        out["message"] = "The deadline has already passed. Choose a new target date."
        return out

    required = remaining / months
    out["required_monthly"] = round(required, 2)
    out["gap"] = round(required - current, 2)

    if current <= 0:
        out["ratio"] = 0.0
        out["status"] = "off_track"
        out["message"] = (f"Based on your recent pattern, you are not saving anything "
                          f"each month, but this goal needs about "
                          f"₹{required:,.0f}/month.")
        return out

    ratio = current / required
    out["ratio"] = round(ratio, 4)
    out["months_needed_at_current_pace"] = math.ceil(remaining / current)
    out["status"] = "on_track" if ratio >= 1 else "close" if ratio >= 0.8 else "off_track"
    if out["status"] == "on_track":
        out["message"] = (f"Based on your recent pattern, you save about "
                          f"₹{current:,.0f}/month against the ₹{required:,.0f}/month "
                          f"needed. That would cover this goal if the pattern continues.")
    else:
        out["message"] = (f"Based on your recent pattern, you save about "
                          f"₹{current:,.0f}/month but this goal needs "
                          f"₹{required:,.0f}/month, a shortfall of "
                          f"₹{required - current:,.0f}/month.")
    return out


def monthly_category_spend(df, months):
    """Average monthly net spend per category over the baseline months."""
    c = category_spending(df, months)["spend"] / len(months)
    return c.round(2).to_dict()


def gap_drivers(df, months, top=3):
    """Largest discretionary categories: the first place to look for savings."""
    c = pd.Series(monthly_category_spend(df, months))
    c = c[~c.index.isin(ESSENTIAL + NOT_SPENDING)]
    return c[c > 0].sort_values(ascending=False).head(top).to_dict()


def emergency_fund_goal(essential_monthly, target_date, multiple=6, already_saved=0.0):
    """Emergency fund = multiple x monthly essential spending. User can still edit it."""
    return {"name": "Emergency Fund",
            "target_amount": round(multiple * essential_monthly, 2),
            "target_date": target_date, "already_saved": already_saved}


if __name__ == "__main__":
    from pathlib import Path

    from core.analytics import baseline
    from core.categorize import categorize, load_rules
    from core.clean import clean_all

    d = Path("data/synthetic")
    df, report = clean_all([(d / "bank_statement.csv", "bank"),
                            (d / "bank_statement.xlsx", "bank"),
                            (d / "card_statement.csv", "card")])
    df = categorize(df, load_rules())
    b = baseline(df, report["baseline_months"])
    goal = {"name": "Japan Trip", "target_amount": 120000,
            "target_date": "2027-06-06", "already_saved": 20000}
    r = evaluate_goal(goal, b["savings_mean"], today="2026-10-06",
                      low_confidence=report["low_confidence"])
    for k, v in r.items():
        print(f"{k}: {v}")
    print("drivers:", gap_drivers(df, report["baseline_months"]))