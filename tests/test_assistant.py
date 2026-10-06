import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from ai.assistant import (QUESTIONS, AssistantUnavailable, explain,
                          numbers_are_verified)
from core.categorize import categorize, load_rules
from core.clean import clean_all

DIR = ROOT / "data" / "synthetic"
FILES = [(DIR / "bank_statement.csv", "bank"),
         (DIR / "bank_statement.xlsx", "bank"),
         (DIR / "card_statement.csv", "card")]
GOAL = {"name": "Japan Trip", "target_amount": 120000,
        "target_date": "2027-06-06", "already_saved": 20000}


def _ctx():
    df, rep = clean_all(FILES)
    return {"df": categorize(df, load_rules()), "months": rep["baseline_months"],
            "low": rep["low_confidence"], "goal": GOAL, "today": date(2026, 10, 6)}


def test_every_menu_question_has_facts():
    ctx = _ctx()
    for key in QUESTIONS.values():
        r = explain(key, ctx, use_ai=False)
        assert r["source"] == "deterministic" and r["text"].strip()


def test_ai_off_never_calls_the_model():
    def boom(prompt):
        raise AssertionError("model must not be called when AI is off")
    explain("goal_gap", _ctx(), use_ai=False, ask=boom)


def test_valid_ai_answer_is_used():
    ctx = _ctx()
    plain = explain("goal_gap", ctx, use_ai=False)["text"]
    r = explain("goal_gap", ctx, ask=lambda p: "In short: " + plain)
    assert r["source"] == "ai"


def test_invented_number_is_rejected():
    r = explain("goal_gap", _ctx(), ask=lambda p: "You will save ₹999,999 every month.")
    assert r["source"] == "deterministic" and "unverified" in r["note"]


def test_unavailable_model_falls_back():
    def down(prompt):
        raise AssistantUnavailable("not running")
    r = explain("goal_gap", _ctx(), ask=down)
    assert r["source"] == "deterministic" and r["text"]


def test_unknown_question_rejected():
    with pytest.raises(ValueError):
        explain("write_sql", _ctx(), use_ai=False)
    assert numbers_are_verified("about ₹12,500", "needs ₹12,500 per month")
    assert not numbers_are_verified("about ₹13,000", "needs ₹12,500 per month")