"""Stage 1: read bank/card statements (CSV, XLSX) into one standard table."""
from pathlib import Path

import pandas as pd
import re

HEADER_WORDS = ["date", "narration", "particulars", "description", "merchant",
                "amount", "debit", "credit", "withdrawal", "deposit", "balance"]
FOOTER_WORDS = ("total", "closing balance", "opening balance", "grand total")


def read_raw(path):
    """Read the file with no header and all values as text."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"File not found: {path.name}")
    ext = path.suffix.lower()
    if ext not in (".csv", ".xlsx", ".xls", ".pdf"):
        raise ValueError(f"Unsupported file type '{ext}'. Please upload CSV, XLSX or PDF.")
    if ext == ".pdf":
        return read_pdf_raw(path)
    try:
        if ext == ".csv":
            raw = pd.read_csv(path, header=None, dtype=str, encoding="utf-8-sig")
        else:
            raw = pd.read_excel(path, header=None, dtype=str)
    except pd.errors.EmptyDataError:
        raise ValueError(f"{path.name} is empty.")
    except Exception as e:
        raise ValueError(f"Could not read {path.name}: {e}")
    if raw.dropna(how="all").empty:
        raise ValueError(f"{path.name} has no data.")
    return raw

def read_pdf_raw(path):
    """Extract the transaction table from a text-based PDF (no OCR)."""
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    rows, has_text, header_seen = [], False, False
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                has_text = has_text or bool((page.extract_text() or "").strip())
                for table in page.extract_tables():
                    for row in table:
                        cells = [None if c is None else c.replace("\n", " ").strip() for c in row]
                        if not any(cells):
                            continue
                        is_header = sum(any(w in c.lower() for w in HEADER_WORDS)
                                        for c in cells if c) >= 3
                        if is_header and header_seen:
                            continue                      # repeated header on later pages
                        header_seen = header_seen or is_header
                        rows.append(cells)
    except Exception as e:
        inner = e.args[0] if e.args else None
        names = {type(e).__name__, type(inner).__name__}
        if (isinstance(inner, PDFPasswordIncorrect) or isinstance(e, PDFPasswordIncorrect)
                or "password" in str(e).lower() or "password" in str(inner).lower()
                or names & {"PDFPasswordIncorrect", "PasswordError"}
                or type(e).__name__ == "PdfminerException"):
            raise ValueError(f"{Path(path).name} is password-protected or cannot be opened. "
                             "Remove the password or download a CSV/XLSX statement instead.")
        raise ValueError(f"Could not read {Path(path).name} as a PDF: {type(e).__name__} {e}")

    if not has_text:
        raise ValueError(f"{Path(path).name} looks like a scanned image. Scanned PDFs are "
                         "not supported. Please use a CSV/XLSX statement.")
    if not rows:
        raise ValueError(f"No transaction table found in {Path(path).name}. This PDF layout "
                         "is not supported. Please use a CSV/XLSX statement.")
    return pd.DataFrame(rows)

def find_header_row(raw, max_scan=30):
    """Return the index of the first row that looks like column names."""
    for i in range(min(max_scan, len(raw))):
        cells = [str(c).strip().lower() for c in raw.iloc[i] if pd.notna(c)]
        hits = sum(any(w in c for w in HEADER_WORDS) for c in cells)
        if hits >= 3:
            return i
    raise ValueError("Could not find a header row (expected columns like Date, "
                     "Description, Amount). Please check the file.")


def extract_table(raw):
    """Use the header row as column names; drop empty and footer rows."""
    h = find_header_row(raw)
    cols = [str(c).strip() if pd.notna(c) else f"col{j}" for j, c in enumerate(raw.iloc[h])]
    df = raw.iloc[h + 1:].copy()
    df.columns = cols
    df = df.dropna(how="all")
    first = df.iloc[:, 0].fillna("").str.strip().str.lower()
    is_footer = first.str.startswith(FOOTER_WORDS)
    df = df[~is_footer & (first != "")]
    return df.reset_index(drop=True)


def load_file(path):
    """Read one statement file and return the standard table."""
    path = Path(path)
    return map_columns(extract_table(read_raw(path)), path.name)


def parse_amount(x):
    """'-₹1,234.50' / '(500)' / '1,250.00 Dr' / '300 Cr' -> signed float. Blank -> NaN."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return float("nan")
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return float("nan")
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    low = s.lower()
    if low.endswith("dr") or low.endswith("dr."):
        neg = True
    s = re.sub(r"[^\d.]", "", s)          # keep digits and the decimal point only
    if s == "":
        return float("nan")
    val = float(s)
    return -val if neg else val


DATE_FORMATS = ["%d/%m/%Y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d %b %Y"]


def parse_date(x):
    s = str(x).strip()
    for fmt in DATE_FORMATS:
        try:
            return pd.to_datetime(s, format=fmt)
        except ValueError:
            continue
    return pd.NaT


def find_col(columns, words):
    """First column whose name contains any of the words."""
    for c in columns:
        if any(w in c.lower() for w in words):
            return c
    return None


def map_columns(df, source_file):
    """Return the standard table: date, description, amount, balance, source_file."""
    date_c = find_col(df.columns, ["date"])
    desc_c = find_col(df.columns, ["narration", "particulars", "description", "merchant"])
    bal_c = find_col(df.columns, ["balance"])
    wd_c = find_col(df.columns, ["withdrawal", "debit"])
    dep_c = find_col(df.columns, ["deposit", "credit"])
    amt_c = find_col(df.columns, ["amount"])

    if date_c is None or desc_c is None:
        raise ValueError("Could not detect Date and Description columns. "
                         "Please map the columns manually.")

    if wd_c and dep_c:
        wd = df[wd_c].map(parse_amount).abs().fillna(0)
        dep = df[dep_c].map(parse_amount).abs().fillna(0)
        amount = dep - wd
    elif amt_c:
        amount = df[amt_c].map(parse_amount)
    else:
        raise ValueError("Could not detect an Amount (or Withdrawal/Deposit) column. "
                         "Please map the columns manually.")

    out = pd.DataFrame({
        "date": df[date_c].map(parse_date),
        "description": df[desc_c].fillna("").astype(str),
        "amount": amount,
        "balance": df[bal_c].map(parse_amount) if bal_c else float("nan"),
        "source_file": source_file,
    })
    keep = ~(out["description"].str.upper().str.strip().isin(["OPENING BALANCE", "BALANCE B/F"])
             & (out["amount"].fillna(0) == 0))
    out = out[keep].reset_index(drop=True)    
    bad = out["date"].isna() | out["amount"].isna()
    if bad.any():
        raise ValueError(f"{int(bad.sum())} rows in {source_file} have an unreadable "
                         f"date or amount (first bad row: {int(bad.idxmax()) + 1}).")
    return out

def reconcile_balance(df, tol=0.01):
    """Check each row: balance change == amount. Returns (ok, list of bad row numbers)."""
    if df["balance"].isna().all():
        return None, []           # no balance column -> cannot check
    diff = df["balance"].diff() - df["amount"]
    bad = diff.abs() > tol
    bad.iloc[0] = False           # first row has no previous balance
    return (not bad.any()), (bad[bad].index + 1).tolist()


if __name__ == "__main__":
    for name in ["bank_statement.csv", "bank_statement.xlsx", "card_statement.csv"]:
        t = load_file(Path("data/synthetic") / name)
        print(name, "->", t.shape)
        print(t.head(3).to_string())
        print("sum of amounts:", round(t["amount"].sum(), 2), "\n")