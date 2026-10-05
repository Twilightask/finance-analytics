"""Synthetic data generator: builds TRUE transactions first, messy files later."""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook

random.seed(42)

# 12 months: Oct 2025 .. Sep 2026
MONTHS = [(2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 10)]

events = []  # every true transaction lives here


def add(d, desc, amount, category, txn_type, account="bank", one_time=False):
    events.append({
        "date": d, "description": desc, "amount": round(amount, 2),
        "category": category, "txn_type": txn_type,
        "account": account, "one_time": one_time,
    })


def build_fixed_items():
    for y, m in MONTHS:
        add(date(y, m, 1), "SALARY ACME TECH PVT LTD", 60000, "Salary", "income")
        add(date(y, m, 2), "RENT TO LANDLORD", -18000, "Rent/Housing", "expense")
        add(date(y, m, 5), "SIP HDFC MUTUAL FUND", -5000, "Investment/Savings", "investment")
        add(date(y, m, 7), "BESCOM ELECTRICITY", -random.randint(900, 1600), "Bills & Utilities", "expense")
        add(date(y, m, 8), "AIRTEL BROADBAND", -999, "Bills & Utilities", "expense")
        add(date(y, m, 9), "JIO MOBILE RECHARGE", -299, "Bills & Utilities", "expense")
    # one-time income (must NOT count in baseline savings)
    add(date(2026, 3, 15), "BONUS ACME TECH", 30000, "Other Income", "income", one_time=True)
    add(date(2026, 7, 20), "INCOME TAX REFUND", 8000, "Other Income", "income", one_time=True)

# category: (merchants, transactions per month, min amount, max amount)
SPENDING = {
    "Food": (["SWIGGY", "ZOMATO", "CAFE COFFEE DAY", "DOMINOS PIZZA"], (6, 10), 150, 700),
    "Groceries": (["BIGBASKET", "DMART", "BLINKIT"], (3, 5), 300, 1800),
    "Shopping": (["AMAZON", "FLIPKART", "MYNTRA"], (1, 3), 500, 4000),
    "Transport": (["UBER", "OLA", "NAMMA METRO"], (6, 10), 60, 450),
    "Entertainment": (["NETFLIX", "BOOKMYSHOW", "SPOTIFY"], (1, 3), 150, 900),
    "Healthcare": (["APOLLO PHARMACY", "PRACTO"], (0, 1), 200, 1500),
}


def build_variable_spending():
    for y, m in MONTHS:
        for category, (merchants, (lo, hi), amin, amax) in SPENDING.items():
            for _ in range(random.randint(lo, hi)):
                d = date(y, m, random.randint(10, 28))
                desc = random.choice(merchants)
                add(d, desc, -random.randint(amin, amax), category, "expense")


def build_anomalies():
    add(date(2025, 12, 22), "MAKEMYTRIP GOA TRIP", -28000, "Travel", "expense")
    add(date(2026, 4, 18), "CROMA LAPTOP", -45000, "Shopping", "expense")
    add(date(2026, 8, 12), "APOLLO HOSPITAL", -22000, "Healthcare", "expense")


def build_identical_pairs():
    # two real purchases, same day, same shop, same amount -> must NOT be deduplicated
    for d in [date(2025, 11, 14), date(2026, 2, 20), date(2026, 6, 9)]:
        add(d, "CHAI POINT", -50, "Food", "expense")
        add(d, "CHAI POINT", -50, "Food", "expense")


def build_extra_investments():
    for y, m in MONTHS:
        add(date(y, m, 6), "RD HDFC BANK", -2000, "Investment/Savings", "investment")
    add(date(2026, 3, 28), "PPF DEPOSIT SBI", -10000, "Investment/Savings", "investment")
    add(date(2026, 1, 12), "ZERODHA BROKERAGE TRANSFER", -15000, "Investment/Savings", "investment")


def build_transfers():
    for d in [date(2025, 11, 3), date(2026, 1, 3), date(2026, 4, 3), date(2026, 7, 3)]:
        add(d, "TRANSFER TO OWN SAVINGS AC", -10000, "Transfer", "transfer")


def build_card_and_payments():
    card_cats = ["Food", "Shopping", "Entertainment"]
    for y, m in MONTHS:
        month_total = 0
        for _ in range(random.randint(3, 4)):
            cat = random.choice(card_cats)
            amt = -random.randint(300, 2000)
            add(date(y, m, random.randint(10, 25)), random.choice(SPENDING[cat][0]),
                amt, cat, "expense", account="card")
            month_total += amt
        # bank pays the card bill: excluded from expenses (card spend already counted)
        add(date(y, m, 28), "CREDIT CARD BILL PAYMENT HDFC", month_total, "Transfer", "cc_payment")


def build_upi_and_reimbursements():
    friends = ["RAHUL SHARMA", "PRIYA NAIR", "AMIT VERMA", "NEHA GUPTA", "KARAN SHAH", "SNEHA RAO"]
    dates = [date(2025, 11, 16), date(2026, 1, 18), date(2026, 3, 21),
             date(2026, 5, 17), date(2026, 7, 19), date(2026, 9, 15)]
    outs = []
    for d, f in zip(dates, friends):
        amt = -random.randint(5, 25) * 100          # multiples of 100
        add(d, "UPI " + f, amt, "Other", "expense")
        outs.append((d, f, amt))
    for d, f, amt in outs[:3]:                       # first 3 get half paid back
        add(d + timedelta(days=2), "UPI RECEIVED " + f, -amt // 2, "Other", "reimbursement")


def build_refunds():
    shopping = [e for e in events
                if e["category"] == "Shopping" and e["account"] == "bank" and e["amount"] > -10000]
    for e in random.sample(shopping, 3):
        add(e["date"] + timedelta(days=2), "REFUND " + e["description"],
            -e["amount"], "Shopping", "refund")


OUT = Path(__file__).parent
OPENING_BALANCE = 100000
mess_rng = random.Random(7)  # separate generator: does not disturb earlier numbers


def messy(desc):
    r = mess_rng.random()
    if r < 0.10:
        return f"UPI/{mess_rng.randint(100000000000, 999999999999)}/{desc}"
    if r < 0.18:
        return "  ".join(desc.split())            # double spaces
    if r < 0.24:
        return desc.lower()
    if r < 0.30:
        return f"{desc} REF{mess_rng.randint(10000, 99999)}"
    return desc


def money_text(x):
    s = f"{abs(x):,.2f}"
    if mess_rng.random() < 0.25:
        s = "₹" + s
    return ("-" if x < 0 else "") + s


def prepare_bank_rows():
    bank = sorted((e for e in events if e["account"] == "bank"), key=lambda e: e["date"])
    bal, rows = OPENING_BALANCE, []
    for e in bank:
        bal = round(bal + e["amount"], 2)
        rows.append({"date": e["date"], "desc": messy(e["description"]),
                     "amount": e["amount"], "balance": bal})
    return rows


def write_bank_csv(rows):
    with open(OUT / "bank_statement.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Narration", "Amount", "Balance"])
        for r in rows:
            w.writerow([r["date"].strftime("%d/%m/%Y"), r["desc"],
                        money_text(r["amount"]), f"{r['balance']:.2f}"])


def write_bank_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["HDFC BANK - STATEMENT OF ACCOUNT"])
    ws.append(["Account No: XXXXXX1234"])
    ws.append([f"Period: {rows[0]['date']:%d-%b-%Y} to {rows[-1]['date']:%d-%b-%Y}"])
    ws.append(["Txn Date", "Particulars", "Withdrawal", "Deposit", "Closing Balance"])
    total_w = total_d = 0
    for r in rows:
        w_amt = -r["amount"] if r["amount"] < 0 else None
        d_amt = r["amount"] if r["amount"] > 0 else None
        total_w += w_amt or 0
        total_d += d_amt or 0
        ws.append([r["date"].strftime("%d-%b-%Y"), r["desc"], w_amt, d_amt, r["balance"]])
    ws.append(["TOTAL", None, total_w, total_d, None])   # footer row to be dropped by ingestion
    wb.save(OUT / "bank_statement.xlsx")


def write_card_csv():
    card = sorted((e for e in events if e["account"] == "card"), key=lambda e: e["date"])
    with open(OUT / "card_statement.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Merchant", "Amount"])
        for e in card:
            w.writerow([e["date"].strftime("%d/%m/%Y"), messy(e["description"]),
                        f"{abs(e['amount']):,.2f} Dr"])
    return len(card)


def write_truth_files(rows_bank_count, rows_card_count):
    # clean truth transactions
    with open(OUT / "truth_transactions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "description", "amount", "category", "txn_type", "account", "one_time"])
        for e in sorted(events, key=lambda e: e["date"]):
            w.writerow([e["date"].isoformat(), e["description"], e["amount"],
                        e["category"], e["txn_type"], e["account"], e["one_time"]])

    def month(e):
        return e["date"].strftime("%Y-%m")

    spend_types = ("expense", "refund", "reimbursement")   # refunds/reimbursements net against spending
    income = [e for e in events if e["txn_type"] == "income" and not e["one_time"]]
    spend = [e for e in events if e["txn_type"] in spend_types]

    total_income = round(sum(e["amount"] for e in income), 2)
    total_expenses = round(-sum(e["amount"] for e in spend), 2)

    monthly = {}
    for mm in sorted({month(e) for e in events}):
        inc = sum(e["amount"] for e in income if month(e) == mm)
        exp = -sum(e["amount"] for e in spend if month(e) == mm)
        monthly[mm] = {"income": round(inc, 2), "expenses": round(exp, 2),
                       "savings": round(inc - exp, 2)}

    by_cat = {}
    for e in spend:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) - e["amount"]

    truth = {
        "total_baseline_income": total_income,
        "total_expenses_net": total_expenses,
        "total_savings": round(total_income - total_expenses, 2),
        "total_investments": round(-sum(e["amount"] for e in events if e["txn_type"] == "investment"), 2),
        "one_time_income": round(sum(e["amount"] for e in events if e["one_time"]), 2),
        "monthly": monthly,
        "category_expenses_net": {k: round(v, 2) for k, v in sorted(by_cat.items())},
        "counts": {
            "total_events": len(events),
            "bank_rows": rows_bank_count,
            "card_rows": rows_card_count,
            "overlap_duplicates": 5,
            "identical_pairs": 3,
            "refunds": sum(e["txn_type"] == "refund" for e in events),
            "transfers": sum(e["txn_type"] == "transfer" for e in events),
            "cc_payments": sum(e["txn_type"] == "cc_payment" for e in events),
            "upi_to_friends": sum(e["description"].startswith("UPI ") and e["txn_type"] == "expense" for e in events),
            "reimbursements": sum(e["txn_type"] == "reimbursement" for e in events),
        },
    }
    with open(OUT / "ground_truth.json", "w", encoding="utf-8") as f:
        json.dump(truth, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    build_fixed_items()
    build_variable_spending()
    build_anomalies()
    build_identical_pairs()
    build_extra_investments()
    build_transfers()
    build_card_and_payments()
    build_upi_and_reimbursements()
    build_refunds()

    rows = prepare_bank_rows()
    cutoff = sum(1 for r in rows if r["date"] < date(2026, 7, 1))
    csv_rows = rows[:cutoff]
    xlsx_rows = rows[cutoff - 5:]          # last 5 CSV rows repeat = overlap duplicates

    write_bank_csv(csv_rows)
    write_bank_xlsx(xlsx_rows)
    n_card = write_card_csv()
    write_truth_files(len(rows), n_card)

    print("bank rows total:", len(rows), "| card rows:", n_card)
    print("csv rows:", len(csv_rows), "| xlsx rows:", len(xlsx_rows))
    print("csv + xlsx - 5 overlap == all bank rows:", len(csv_rows) + len(xlsx_rows) - 5 == len(rows))
    print("closing balance ok:", rows[-1]["balance"] ==
          round(OPENING_BALANCE + sum(e["amount"] for e in events if e["account"] == "bank"), 2))