# Goal-Based Personal Finance Analytics

Most budgeting apps tell you where your money went. This one answers a different
question: **based on my actual spending and saving, can I reach my financial goal?**

**Live demo (synthetic data):** _add link after deployment_

![Overview](docs/overview.png)
![Goal and what-if](docs/goal.png)

## What it does
- Reads bank/credit-card statements (CSV, XLSX, text-based PDF for one tested layout)
- Cleans messy data: preamble/footer rows, dd/mm dates, Dr/Cr and ₹ formats, duplicates
- Handles money edge cases: transfers, credit-card bill payments, refunds, reimbursements,
  investments counted as savings, one-time income excluded from the baseline
- Rule-based categorization with user corrections saved as rules
- Analytics: monthly income/expenses/savings, category split, recurring payments,
  IQR anomalies, essential vs discretionary
- Goal engine: required monthly saving, gap, status (on track / close / off track)
- Deterministic what-if simulator (cut a category, add savings, move the deadline)
- Optional local AI (Ollama) that only rewords verified results; any reply containing
  a number not in the verified facts is discarded

## How correctness was checked
The synthetic data generator writes a known-answer file (`ground_truth.json`) before any
messing-up happens. The pipeline must reproduce it exactly:
income ₹7,20,000, net expenses ₹5,91,602, savings ₹1,28,398.
78 automated tests cover this, plus balance reconciliation and edge cases.

## Limits (honest)
- PDF support covers one tested layout. Other layouts and scanned PDFs show a clear message.
- Savings are assumed to continue at the recent average. The app never promises success.
- Not investment advice. One active goal only.

## Run locally
```
pip install -r requirements.txt
streamlit run app/streamlit_app.py
pytest
```
Optional AI: install Ollama, run `ollama pull llama3.2:3b`, then use the AI Assistant page.

## Privacy
Your data stays on your computer. The public demo uses synthetic data only, with uploads
and AI disabled (`DEMO_MODE=1`).

## Structure
`core/` ingest, clean, categorize, analytics, goals, db · `ai/` assistant ·
`app/` Streamlit UI (display only) · `data/synthetic/` generator and answer key · `tests/`