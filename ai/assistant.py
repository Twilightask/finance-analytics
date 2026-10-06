"""Stage 9: optional AI explainer. Numbers come from core/; the model only words them."""
import json
import re
import urllib.request

from core.analytics import (baseline, category_spending, essential_split,
                            find_anomalies, recurring_payments)
from core.goals import evaluate_goal, gap_drivers

OLLAMA_URL = "http://localhost:11434/api/generate"   # local only: data never leaves your PC
MODEL = "llama3.2:3b"


class AssistantUnavailable(Exception):
    pass


def _r(x):
    return f"₹{x:,.0f}"


# ---------- whitelisted fact builders (ctx = df, months, goal, today, low) ----------
def goal_gap(c):
    b = baseline(c["df"], c["months"])
    r = evaluate_goal(c["goal"], b["savings_mean"], c["today"], c["low"])
    lines = [r["message"]]
    if r["gap"] is not None and r["gap"] > 0:
        d = gap_drivers(c["df"], c["months"])
        if d:
            lines.append("Biggest discretionary categories per month: "
                         + ", ".join(f"{k} {_r(v)}" for k, v in d.items()) + ".")
    return lines + r["warnings"]


def top_categories(c):
    cats = category_spending(c["df"], c["months"]).head(5)
    lines = [f"Spending over the last {len(c['months'])} complete months:"]
    lines += [f"{name}: {_r(row.spend)} ({row.share_pct}% of spending)"
              for name, row in cats.iterrows()]
    return lines


def stability(c):
    b = baseline(c["df"], c["months"])
    lines = [f"Average monthly savings {_r(b['savings_mean'])}, median {_r(b['savings_median'])}.",
             f"Average monthly income {_r(b['income_mean'])}."]
    if b["savings_skewed"]:
        lines.append("Average and median savings differ by more than 20%, so a few unusual "
                     "months are pulling the average.")
    if b["income_unstable"]:
        lines.append("Income varies a lot from month to month.")
    return lines


def recurring(c):
    r = recurring_payments(c["df"]).head(5)
    if r.empty:
        return ["No recurring payments were found."]
    return ["Recurring payments:"] + [
        f"{x.merchant}: {_r(x.typical_amount)} per month, seen in {x.months} months"
        for x in r.itertuples()]


def anomalies(c):
    a = find_anomalies(c["df"]).head(5)
    if a.empty:
        return ["No unusually large expenses were found."]
    return ["Unusually large expenses:"] + [
        f"{x.date:%Y-%m-%d} {x.description_clean}: {_r(x.spend)} ({x.category})"
        for x in a.itertuples()]


def emergency(c):
    s = essential_split(c["df"], c["months"])
    return [f"Essential spending is about {_r(s['essential_monthly'])} per month.",
            f"An emergency fund of 3 to 6 months of essentials is "
            f"{_r(s['emergency_fund_3x'])} to {_r(s['emergency_fund_6x'])}."]


QUESTIONS = {
    "Why am I struggling to reach my goal?": "goal_gap",
    "Where does my money go?": "top_categories",
    "How stable are my income and savings?": "stability",
    "What are my recurring payments?": "recurring",
    "Which expenses were unusual?": "anomalies",
    "How big should my emergency fund be?": "emergency",
}
FUNCS = {"goal_gap": goal_gap, "top_categories": top_categories, "stability": stability,
         "recurring": recurring, "anomalies": anomalies, "emergency": emergency}


# ---------- safety layer ----------
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers(text):
    return {float(m.replace(",", "")) for m in NUM.findall(text)}


def numbers_are_verified(answer, facts_text):
    """True only if the answer contains no number that is absent from the facts."""
    return numbers(answer) <= numbers(facts_text)


def build_prompt(facts_text):
    return ("You explain verified personal-finance results in simple English.\n"
            "Rules: use ONLY the facts below. Do not add, change, round or calculate any "
            "number. Do not give investment advice. Do not promise the goal will be "
            "achieved. Maximum 100 words.\n\nFACTS:\n" + facts_text + "\n\nEXPLANATION:")


def ask_ollama(prompt, model=MODEL, url=OLLAMA_URL, timeout=90):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())["response"].strip()
    except Exception as e:
        raise AssistantUnavailable(f"Ollama is not available: {e}")


def explain(key, ctx, use_ai=True, ask=ask_ollama):
    """Returns {'text', 'source': 'ai' | 'deterministic', 'note'}."""
    if key not in FUNCS:
        raise ValueError(f"Unsupported question '{key}'.")
    facts_text = "\n".join(FUNCS[key](ctx))
    plain = {"text": facts_text, "source": "deterministic", "note": ""}
    if not use_ai:
        return plain
    try:
        answer = ask(build_prompt(facts_text))
    except AssistantUnavailable:
        plain["note"] = "AI is not running, so the verified facts are shown."
        return plain
    if not answer or not numbers_are_verified(answer, facts_text):
        plain["note"] = "The AI reply contained unverified numbers, so it was discarded."
        return plain
    return {"text": answer, "source": "ai", "note": ""}


if __name__ == "__main__":
    from datetime import date
    from pathlib import Path

    from core.categorize import categorize, load_rules
    from core.clean import clean_all

    d = Path("data/synthetic")
    df, rep = clean_all([(d / "bank_statement.csv", "bank"),
                         (d / "bank_statement.xlsx", "bank"),
                         (d / "card_statement.csv", "card")])
    df = categorize(df, load_rules())
    ctx = {"df": df, "months": rep["baseline_months"], "low": rep["low_confidence"],
           "today": date(2026, 10, 6),
           "goal": {"name": "Japan Trip", "target_amount": 120000,
                    "target_date": "2027-06-06", "already_saved": 20000}}
    for label, key in QUESTIONS.items():
        print("Q:", label)
        print(explain(key, ctx, use_ai=False)["text"], "\n")