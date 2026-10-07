"""Stage 7: Streamlit UI. Displays results only; all logic lives in core/."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core.categorize import (categorize, correct_category, coverage,
                             load_rules, load_user_rules)
from core.clean import clean_all
from core.db import load_goal, load_transactions, save_goal, save_transactions
from core.goals import (NOT_SPENDING, emergency_fund_goal, evaluate_goal,
                        gap_drivers, monthly_category_spend, simulate)
import plotly.express as px

from core.analytics import (ESSENTIAL, baseline, category_spending, essential_split,
                            find_anomalies, month_over_month, monthly_summary,
                            overview, recurring_payments, top_merchants)
from core.clean import quality_report

from ai.assistant import QUESTIONS, explain


DEMO = ROOT / "data" / "synthetic"
DEMO_FILES = [(DEMO / "bank_statement.csv", "bank"),
              (DEMO / "bank_statement.xlsx", "bank"),
              (DEMO / "card_statement.csv", "card")]

st.set_page_config(page_title="Goal-Based Finance Analytics", layout="wide")
DEMO_MODE = os.environ.get("DEMO_MODE") == "1"


def run_pipeline(files):
    """files = list of (path, account_type). Stores results in session_state + SQLite."""
    df, report = clean_all(files)
    df = categorize(df, load_rules(), load_user_rules())
    if not DEMO_MODE:
        save_transactions(df)
    st.session_state["df"] = df
    st.session_state["report"] = report


def get_data():
    """Current table: from this session, else from SQLite, else None."""
    if "df" not in st.session_state and not DEMO_MODE:
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

    if DEMO_MODE:
        st.info("Public demo: uploads are disabled and only synthetic data is used. "
                "Run the app locally to analyse your own statements.")
        uploads = []
    else:
        uploads = st.file_uploader("Statement files", type=["csv", "xlsx", "pdf"],
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
    c2.caption("Date range")
    c2.markdown(f"**{df['date'].min():%d %b %Y} to {df['date'].max():%d %b %Y}**")
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

def rupee_labels(values):
    """Indian-style labels for chart text: 62000 -> ₹62,000 (display only)."""
    return [f"₹{v:,.0f}" for v in values]


def month_label(s):
    """'2026-07' -> 'Jul 2026'."""
    return pd.to_datetime(s + "-01").strftime("%b %Y")


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
    c1.metric("Baseline income", rupees(o["baseline_income"]))
    c2.metric("Net expenses", rupees(o["total_expenses"]))
    c3.metric("Cash savings", rupees(o["cash_savings"]))
    c4.metric("Cash savings rate", f"{o['cash_savings_rate'] * 100:.1f}%" if o["cash_savings_rate"] is not None else "n/a")
    e1, e2, e3 = st.columns(3)
    e1.metric("Investment contributions", rupees(o["investment_contributions"]))
    e2.metric("Total savings (cash + investments)", rupees(o["total_savings"]))
    e3.metric("Total savings rate", f"{o['total_savings_rate'] * 100:.1f}%" if o["total_savings_rate"] is not None else "n/a")
    st.caption(f"One-time income excluded: {rupees(o['one_time_income'])}. Net expenses are after "
               "refunds and reimbursements. Goals use cash savings, not investments.")

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
    m["label"] = m["month"].map(month_label)
    month_order = m["label"].tolist()

    # 1) income vs expenses
    inc_exp = m.melt(id_vars=["month", "label"], value_vars=["income", "expenses"],
                     var_name="type", value_name="amount")
    fig1 = px.bar(inc_exp, x="label", y="amount", color="type", barmode="group",
                  text=rupee_labels(inc_exp["amount"]),
                  category_orders={"label": month_order},
                  labels={"label": "Month", "amount": "Amount (₹)", "type": ""},
                  title="Monthly income vs expenses")
    fig1.update_traces(textposition="outside", cliponaxis=False,
                       hovertemplate="%{x}<br>%{fullData.name}: ₹%{y:,.0f}<extra></extra>")
    fig1.update_xaxes(type="category")

    # 2) monthly savings
    fig2 = px.bar(m, x="label", y="savings", text=rupee_labels(m["savings"]),
                  category_orders={"label": month_order},
                  labels={"label": "Month", "savings": "Cash savings (₹)"},
                  title="Monthly savings")
    fig2.update_traces(textposition="outside", cliponaxis=False,
                       hovertemplate="%{x}<br>Savings: ₹%{y:,.0f}<extra></extra>")
    fig2.update_xaxes(type="category")

    left, right = st.columns(2)
    left.plotly_chart(fig1, use_container_width=True)
    right.plotly_chart(fig2, use_container_width=True)

    cats = category_spending(df).reset_index().sort_values("spend")
    fig3 = px.bar(cats, x="spend", y="category", orientation="h",
                  text=rupee_labels(cats["spend"]),
                  labels={"spend": "Spend (₹)", "category": ""},
                  title="Spending by category")
    fig3.update_traces(textposition="outside", cliponaxis=False,
                       hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>")

    m["change_pct"] = month_over_month(m.set_index("month")).values
    fig4 = px.line(m, x="label", y="expenses", markers=True,
                   text=rupee_labels(m["expenses"]),
                   category_orders={"label": month_order},
                   hover_data={"change_pct": True, "label": False},
                   labels={"label": "Month", "expenses": "Expenses (₹)",
                           "change_pct": "Change vs prev. month (%)"},
                   title="Spending trend")
    fig4.update_traces(textposition="top center")
    fig4.update_xaxes(type="category")
    fig4.update_yaxes(rangemode="tozero")

    left, right = st.columns(2)
    left.plotly_chart(fig3, use_container_width=True)
    right.plotly_chart(fig4, use_container_width=True)

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

CATEGORIES = ["Food", "Groceries", "Shopping", "Transport", "Bills & Utilities",
              "Entertainment", "Healthcare", "Education", "Rent/Housing", "Travel",
              "EMI/Loan", "Insurance", "Fees & Charges", "Cash Withdrawal",
              "Investment/Savings", "Salary", "Other Income", "Transfer", "Other"]


def fmt(x):
    return rupees(x) if x is not None else "n/a"


def init_goal_state():
    if "g_name" in st.session_state:
        return
    g = None if DEMO_MODE else load_goal()
    if g:
        st.session_state["g_name"] = g["name"]
        st.session_state["g_target"] = float(g["target_amount"])
        st.session_state["g_date"] = pd.Timestamp(g["target_date"]).date()
        st.session_state["g_saved"] = float(g["already_saved"])
    else:
        st.session_state["g_name"] = "My Goal"
        st.session_state["g_target"] = 100000.0
        st.session_state["g_date"] = date.today() + timedelta(days=240)
        st.session_state["g_saved"] = 0.0


def show_status(r):
    box = {"on_track": st.success, "close": st.warning, "off_track": st.error}.get(r["status"], st.info)
    box(r["message"])
    for w in r["warnings"]:
        st.warning(w)


STATUS_TEXT = {"on_track": "On track", "close": "Close", "off_track": "Off track",
               "achieved": "Already achieved", "deadline_passed": "Deadline passed"}


def goal_summary(r):
    """One plain sentence explaining a goal result (display only)."""
    if r["status"] in ("achieved", "deadline_passed"):
        return r["message"]
    need, have = r["required_monthly"], r["current_monthly_saving"]
    text = (f"To reach this goal in **{r['months_left']} months** you need to save "
            f"**{rupees(need)} every month**. ")
    if have <= 0:
        return text + "Based on your recent pattern, you are not saving anything each month."
    text += f"Based on your recent pattern you save about **{rupees(have)}** a month. "
    if r["gap"] > 0:
        return text + f"That is **{rupees(r['gap'])} short** each month."
    return text + f"That is **{rupees(-r['gap'])} more** than needed."


def goal_date(today, months):
    """Month the goal is reached if you keep saving at a given pace (display only)."""
    if not months:
        return "not at this pace"
    return (pd.Timestamp(today) + pd.DateOffset(months=int(months))).strftime("%b %Y")


def page_goal():
    st.title("Goal & What-If")
    df = get_data()
    if df is None:
        st.info("No data yet. Go to Upload & Preview first.")
        return
    months, low = baseline_info(df)
    if not months:
        st.error("No complete months found, so a goal cannot be evaluated.")
        return
    b = baseline(df, months)
    init_goal_state()

    st.info("**How this page works**\n\n"
            "1. Tell us what you want to save for, how much, and by when.\n"
            "2. We compare it with what you actually save each month.\n"
            "3. Try changes (spend less, save extra, move the deadline) and see if the goal becomes realistic.")

    # ---------- Step 1 ----------
    st.subheader("Step 1: Your goal")
    if st.button("Use emergency-fund template (6 x essential monthly spending)"):
        sp = essential_split(df, months)
        st.session_state["g_name"] = "Emergency Fund"
        st.session_state["g_target"] = emergency_fund_goal(
            sp["essential_monthly"], date.today())["target_amount"]
    c1, c2, c3, c4 = st.columns(4)
    c1.text_input("Goal name", key="g_name")
    c2.number_input("Target amount (₹)", min_value=0.0, step=1000.0, key="g_target")
    c3.date_input("Deadline", key="g_date")
    c4.number_input("Already saved for this goal (₹)", min_value=0.0, step=1000.0, key="g_saved",
                    help="Statements cannot show this, so enter it yourself.")
    st.caption("One goal at a time, because your monthly savings cannot be split across "
               "several goals reliably.")

    goal = {"name": st.session_state["g_name"], "target_amount": st.session_state["g_target"],
            "target_date": st.session_state["g_date"].isoformat(),
            "already_saved": st.session_state["g_saved"]}
    if not DEMO_MODE and st.button("Save goal"):
        save_goal(goal)
        st.success("Goal saved.")

    # ---------- Step 2 ----------
    st.subheader("Step 2: Can you reach it?")
    today = date.today()
    r = evaluate_goal(goal, b["savings_mean"], today, low)
    st.markdown(goal_summary(r))
    show_status(r)
    if goal["already_saved"] > 0 and goal["target_amount"] > 0:
        st.progress(min(goal["already_saved"] / goal["target_amount"], 1.0),
                    text=f"Already saved: {rupees(goal['already_saved'])} of {rupees(goal['target_amount'])}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Still to save", rupees(r["remaining"]),
              help="Target minus what you have already saved.")
    m2.metric("Months left", r["months_left"] if r["months_left"] is not None else "n/a")
    m3.metric("You need to save / month", fmt(r["required_monthly"]),
              help="Still to save divided by months left.")
    m4.metric("You save / month now", rupees(r["current_monthly_saving"]),
              f"median {rupees(b['savings_median'])}", delta_color="off",
              help="Average cash savings over your recent complete months (income minus spending, "
                   "investments not counted). The median is the middle month.")
    n = r["months_needed_at_current_pace"]
    if n:
        deadline = pd.Timestamp(goal["target_date"]).strftime("%b %Y")
        st.markdown(f"**Estimated finish:** around **{goal_date(today, n)}** "
                    f"at your current pace (your deadline: {deadline}).")

    st.markdown("**How reliable is this?** Your savings change from month to month, "
                "so here is the goal in your best, typical and worst recent month:")
    monthly = monthly_summary(df).loc[months, "savings"]
    rows = []
    for label, val in [("Best month", monthly.max()),
                       ("Typical month (median)", monthly.median()),
                       ("Worst month", monthly.min())]:
        x = evaluate_goal(goal, val, today, low)
        rows.append({"If you save like your...": label,
                     "Saving / month": rupees(val),
                     "Result": STATUS_TEXT.get(x["status"], x["status"]),
                     "Goal reached around": goal_date(today, x["months_needed_at_current_pace"])})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if r["gap"] is not None and r["gap"] > 0:
        drivers = gap_drivers(df, months)
        if drivers:
            st.write("Where you could cut back (biggest optional spending per month): " +
                     ", ".join(f"**{k}** {rupees(v)}" for k, v in drivers.items()))

    # ---------- Step 3 ----------
    st.subheader("Step 3: Try changes (what-if)")
    st.caption("Change anything below and see the result straight away. "
               "Nothing is saved, and it assumes the money you cut is really saved.")
    spend = monthly_category_spend(df, months)
    usable = [c for c, v in spend.items() if v > 0 and c not in NOT_SPENDING]
    cuts = {}
    with st.expander("Spend less in a category", expanded=True):
        for cat in [c for c in usable if c not in ESSENTIAL]:
            cuts[cat] = st.slider(f"{cat}: reduce by % (now {rupees(spend[cat])}/month)",
                                  0, 100, 0, 5, key=f"cut_{cat}")
    with st.expander("Essential categories (rent, bills...)"):
        for cat in [c for c in usable if c in ESSENTIAL]:
            cuts[cat] = st.slider(f"{cat}: reduce by % (now {rupees(spend[cat])}/month)",
                                  0, 100, 0, 5, key=f"cut_{cat}")
    extra = st.number_input("Save an extra amount every month (₹)", min_value=0.0, step=500.0)
    new_deadline = None
    if st.checkbox("Try a different deadline"):
        new_deadline = st.date_input("New deadline", value=goal_default(goal),
                                     key="new_deadline").isoformat()

    s = simulate(goal, b["savings_mean"], spend, today, low,
                 cuts={c: p for c, p in cuts.items() if p > 0},
                 extra_saving=extra, new_deadline=new_deadline)
    cur, sc = s["current"], s["scenario"]

    st.markdown("**Result with your changes**")
    if s["monthly_improvement"] == 0 and new_deadline is None:
        st.caption("No changes yet. Move a slider or add an extra amount above.")
    else:
        st.markdown(goal_summary(sc))
        show_status(sc)
        a, bcol = st.columns(2)
        a.metric("Before: you save / month", rupees(cur["current_monthly_saving"]))
        bcol.metric("After: you save / month", rupees(sc["current_monthly_saving"]),
                    f"+{rupees(s['monthly_improvement'])}")
        st.caption(f"Before: **{STATUS_TEXT.get(cur['status'], cur['status'])}**  →  "
                   f"After: **{STATUS_TEXT.get(sc['status'], sc['status'])}**")

    cmp = pd.DataFrame({"Case": ["Now", "With your changes"],
                        "Monthly saving": [cur["current_monthly_saving"], sc["current_monthly_saving"]]})
    fig = px.bar(cmp, x="Case", y="Monthly saving",
                 text=rupee_labels(cmp["Monthly saving"]),
                 title="Your monthly saving vs what you need")
    fig.update_traces(textposition="outside", cliponaxis=False)
    if sc["required_monthly"] is not None:
        fig.add_hline(y=sc["required_monthly"], line_dash="dash",
                      annotation_text=f"Needed: {rupees(sc['required_monthly'])}")
    st.plotly_chart(fig, use_container_width=True)


def goal_default(goal):
    return pd.Timestamp(goal["target_date"]).date() + timedelta(days=90)


def page_transactions():
    st.title("Transactions & Category Corrections")
    df = get_data()
    if df is None:
        st.info("No data yet. Go to Upload & Preview first.")
        return
    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"))

    f1, f2, f3, f4 = st.columns(4)
    cat = f1.selectbox("Category", ["All"] + sorted(df["category"].unique()))
    typ = f2.selectbox("Type", ["All"] + sorted(df["txn_type"].unique()))
    text = f3.text_input("Search description")
    only_review = f4.checkbox("Needs review only")
    v = df
    if cat != "All":
        v = v[v["category"] == cat]
    if typ != "All":
        v = v[v["txn_type"] == typ]
    if text:
        v = v[v["description_clean"].str.contains(text.upper(), regex=False)]
    if only_review:
        v = v[v["needs_review"]]
    st.write(f"{len(v)} transactions")

    st.subheader("Correct a category")
    if len(v) == 0:
        st.info("No transactions match the filters.")
    else:
        shown = v.head(300)
        names = dict(zip(shown["txn_id"], shown["description_clean"] + "  |  " + shown["amount"].map("{:,.0f}".format)))
        tid = st.selectbox("Transaction", list(names), format_func=lambda i: f"{i}  |  {names[i]}")
        new_cat = st.selectbox("New category", CATEGORIES)
        whole = st.checkbox("Apply to every transaction from this merchant "
                            "(also saved as a rule for future uploads)", value=not DEMO_MODE, disabled=DEMO_MODE)
        if st.button("Apply correction"):
            fixed = correct_category(df, tid, new_cat, apply_to_merchant=whole)
            if not DEMO_MODE:
                save_transactions(fixed)
            st.session_state["df"] = fixed
            st.session_state["flash"] = f"Category changed to {new_cat}."
            st.rerun()

    st.dataframe(v[["txn_id", "date", "description", "amount", "txn_type",
                    "category", "category_source"]].head(300), use_container_width=True)

def page_assistant():
    st.title("AI Assistant")
    st.caption("Pick a question. Numbers always come from the verified calculations. "
               "The AI only rewords them, and any answer with an unverified number is discarded.")
    df = get_data()
    if df is None:
        st.info("No data yet. Go to Upload & Preview first.")
        return
    months, low = baseline_info(df)
    if not months:
        st.error("No complete months found.")
        return
    init_goal_state()
    goal = {"name": st.session_state["g_name"], "target_amount": st.session_state["g_target"],
            "target_date": st.session_state["g_date"].isoformat(),
            "already_saved": st.session_state["g_saved"]}
    ctx = {"df": df, "months": months, "low": low, "goal": goal, "today": date.today()}

    use_ai = st.toggle("Use local AI (Ollama) to reword the answer", value=False)
    label = st.selectbox("Question", list(QUESTIONS))
    if st.button("Answer"):
        with st.spinner("Working..."):
            res = explain(QUESTIONS[label], ctx, use_ai=use_ai)
        st.session_state["answer"] = res
    res = st.session_state.get("answer")
    if res:
        st.write(res["text"])
        if res["source"] == "ai":
            st.caption("Reworded by a local AI. Every number was checked against the verified facts.")
        else:
            st.caption("Shown as verified facts (no AI used).")
        if res["note"]:
            st.info(res["note"])

PAGES = {"Upload & Preview": page_upload, "Financial Overview": page_overview,
         "Goal & What-If": page_goal, "Transactions": page_transactions,
         "AI Assistant": page_assistant}

if DEMO_MODE:
    PAGES.pop("AI Assistant")

page = st.sidebar.radio("Go to", list(PAGES))
PAGES[page]()

st.divider()
st.caption("Credits: Aayush Kumbhar")