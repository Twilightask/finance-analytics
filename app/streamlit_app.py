"""Stage 7: Streamlit UI. Displays results only; all logic lives in core/."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

from core.categorize import categorize, coverage, load_rules, load_user_rules
from core.clean import clean_all
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


PAGES = {"Upload & Preview": page_upload}

page = st.sidebar.radio("Go to", list(PAGES))
PAGES[page]()