"""Stage 4: SQLite persistence (plain sqlite3 + pandas, no ORM)."""
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent.parent / "data" / "finance.db"
BOOL_COLS = ["one_time", "needs_review", "unitemized_card"]


def _table_exists(conn, name):
    q = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
    return conn.execute(q, (name,)).fetchone() is not None


def save_transactions(df, path=DB_PATH):
    with closing(sqlite3.connect(path)) as conn:
        df.to_sql("transactions", conn, if_exists="replace", index=False)


def load_transactions(path=DB_PATH):
    """Returns the saved table, or None if nothing has been saved yet."""
    if not Path(path).exists():
        return None
    with closing(sqlite3.connect(path)) as conn:
        if not _table_exists(conn, "transactions"):
            return None
        df = pd.read_sql("SELECT * FROM transactions", conn, parse_dates=["date"])
    for c in BOOL_COLS:
        if c in df.columns:
            df[c] = df[c].astype(bool)
    return df


def save_goal(goal, path=DB_PATH):
    """goal = dict: name, target_amount, target_date (YYYY-MM-DD), already_saved."""
    with closing(sqlite3.connect(path)) as conn:
        pd.DataFrame([goal]).to_sql("goals", conn, if_exists="replace", index=False)


def load_goal(path=DB_PATH):
    if not Path(path).exists():
        return None
    with closing(sqlite3.connect(path)) as conn:
        if not _table_exists(conn, "goals"):
            return None
        g = pd.read_sql("SELECT * FROM goals", conn)
    return g.iloc[0].to_dict() if len(g) else None