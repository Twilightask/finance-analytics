"""Stage 7: Streamlit UI. Displays results only; all logic lives in core/."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

from core.categorize import categorize, coverage, load_rules, load_user_rules
from core.clean import clean_all
import plotly.express as px

from core.analytics import (baseline, category_spending, essential_split,
                            find_anomalies, month_over_month, monthly_summary,
                            overview, recurring_payments, top_merchants)
from core.clean import quality_report
from core.db import load_transactions, save_transactions

DEMO = ROOT / "data" / "synthetic"
DEMO_FILES = [(DEMO / "bank_statement.csv", "bank"),
              (DEMO / "bank_statement.xlsx", "bank"),
              (DEMO / "card_statement.csv", "card")]

st.set_page_config(page_title="Goal-Based Finance Analytics", layout="wide")


def run_pipeline(files):
    """files = list of (path, account_type). Stores results in session_state + SQLite."""
    df, report = clean_all(files)
    df = categorize(df, load_rules(), load_user_rules())
    save_transactions(df)
    st.session_state["df"] = df
    st.session_state["report"] = report


def get_data():
    """Current table: from this session, else from SQLite, else None."""
    if "df" not in st.session_state:
        saved = load_transactions()
        if saved is not None:
            st.session_state["df"] = saved
    return st.session_state.get("df")


def page_upload():
    st.title("Upload & Preview")
    st.caption("Upload your own bank/credit-card statement (CSV or XLSX). "
               "Data stays on this computer.")

    if st.button("Use synthetic demo data"):
        try:
            run_pipeline(DEMO_FILES)
            st.success("Demo data loaded.")
        except ValueError as e:
            st.error(str(e))

    uploads = st.file_uploader("Statement files", type=["csv", "xlsx"],
                               accept_multiple_files=True)
    kinds = {}
    for f in uploads:
        kinds[f.name] = st.radio(f"{f.name} is a", ["bank", "card"],
                                 horizontal=True, key=f"kind_{f.name}")

    if uploads and st.button("Process uploaded files"):
        tmp = Path(tempfile.mkdtemp())
        files = []
        for f in uploads:
            p = tmp / f.name
            p.write_bytes(f.getvalue())
            files.append((p, kinds[f.name]))
        try:
            run_pipeline(files)
            st.success("Files processed.")
        except ValueError as e:
            st.error(str(e))

    df = get_data()
    if df is None:
        st.info("No data yet. Upload a statement or load the demo data.")
        return

    rep = st.session_state.get("report")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transactions", len(df))
    c2.metric("Date range", f"{df['date'].min():%d %b %Y} to {df['date'].max():%d %b %Y}")
    c3.metric("Categorized by rules", f"{coverage(df)}%")
    c4.metric("Needs review", int(df["needs_review"].sum()))

    if rep:
        st.write(f"Duplicates removed: **{rep['duplicates_removed']}**")
        if rep["balance_ok"] is True:
            st.success("Balance check passed.")
        elif rep["balance_ok"] is False:
            st.warning(f"Balance check failed at rows {rep['balance_bad_rows'][:10]}.")
        if rep["partial_months"]:
            st.warning(f"Partial months excluded from averages: {rep['partial_months']}")
        if rep["low_confidence"]:
            st.warning("Fewer than 3 complete months: results are low confidence.")
        if rep["unitemized_card_payments"]:
            st.warning(f"{rep['unitemized_card_payments']} credit-card bill payments "
                       "counted as spending (no card statement uploaded).")

    st.subheader("Preview")
    st.dataframe(df[["date", "description", "amount", "txn_type", "category"]].head(50),
                 use_container_width=True)


def rupees(x):
    return f"₹{x:,.0f}"


def baseline_info(df):
    """Baseline months + low-confidence flag, from the session or recomputed."""
    rep = st.session_state.get("report")
    if rep:
        return rep["baseline_months"], rep["low_confidence"]
    q = quality_report(df)
    return q["baseline_months"], q["low_confidence"]


def page_overview():
    st.title("Financial Overview")
    df = get_data()
    if df is None:
        st.info("No data yet. Go to Upload & Preview first.")
        return
    months, low = baseline_info(df)
    if not months:
        st.error("No complete months found, so averages cannot be calculated.")
        return

    o, b = overview(df), baseline(df, months)
    if low:
        st.warning("Fewer than 3 complete months: treat these numbers as low confidence.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total income", rupees(o["total_income"]))
    c2.metric("Net expenses", rupees(o["total_expenses"]))
    c3.metric("Net savings", rupees(o["net_savings"]))
    c4.metric("Savings rate", f"{o['savings_rate'] * 100:.1f}%" if o["savings_rate"] is not None else "n/a")
    st.caption(f"Income excludes one-time income ({rupees(o['one_time_income'])}). "
               f"Investments ({rupees(o['total_investments'])}) count as savings, not spending.")

    st.subheader(f"Typical month (last {len(months)} complete months)")
    d1, d2, d3 = st.columns(3)
    d1.metric("Savings: average", rupees(b["savings_mean"]), f"median {rupees(b['savings_median'])}", delta_color="off")
    d2.metric("Expenses: average", rupees(b["expenses_mean"]), f"median {rupees(b['expenses_median'])}", delta_color="off")
    d3.metric("Income: average", rupees(b["income_mean"]), f"median {rupees(b['income_median'])}", delta_color="off")
    if b["savings_skewed"]:
        st.info("Average and median savings differ by more than 20%, so a few unusual "
                "months are pulling the average. Look at the median too.")
    if b["income_unstable"]:
        st.info("Your income varies a lot from month to month, so averages may mislead.")

    m = monthly_summary(df).reset_index()
    left, right = st.columns(2)
    left.plotly_chart(px.bar(m, x="month", y=["income", "expenses"], barmode="group",
                             title="Monthly income vs expenses"), use_container_width=True)
    right.plotly_chart(px.bar(m, x="month", y="savings", title="Monthly savings"),
                       use_container_width=True)

    cats = category_spending(df).reset_index()
    left, right = st.columns(2)
    left.plotly_chart(px.bar(cats.sort_values("spend"), x="spend", y="category",
                             orientation="h", title="Spending by category"),
                      use_container_width=True)
    m["change_pct"] = month_over_month(m.set_index("month")).values
    right.plotly_chart(px.line(m, x="month", y="expenses", markers=True,
                               hover_data=["change_pct"], title="Spending trend"),
                       use_container_width=True)

    sp = essential_split(df, months)
    st.write(f"Essential spending: **{rupees(sp['essential_monthly'])}/month**, "
             f"discretionary: **{rupees(sp['discretionary_monthly'])}/month**. "
             f"Emergency fund (3 to 6 months of essentials): "
             f"**{rupees(sp['emergency_fund_3x'])} to {rupees(sp['emergency_fund_6x'])}**.")

    with st.expander("Top merchants"):
        st.dataframe(top_merchants(df, 10).reset_index(), use_container_width=True)
    with st.expander("Recurring payments"):
        st.dataframe(recurring_payments(df), use_container_width=True)
    with st.expander("Unusually large expenses"):
        st.dataframe(find_anomalies(df), use_container_width=True)

PAGES = {"Upload & Preview": page_upload, "Financial Overview": page_overview}

page = st.sidebar.radio("Go to", list(PAGES))
PAGES[page]()