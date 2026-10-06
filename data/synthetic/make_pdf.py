"""Build a text-based PDF bank statement from the XLSX data (for testing PDF ingestion)."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from core.ingest import load_file


def make_bank_pdf(out_path, password=None):
    df = load_file(ROOT / "data" / "synthetic" / "bank_statement.xlsx")
    data = [["Txn Date", "Particulars", "Withdrawal", "Deposit", "Closing Balance"]]
    for r in df.itertuples():
        data.append([r.date.strftime("%d-%b-%Y"), r.description,
                     f"{-r.amount:,.2f}" if r.amount < 0 else "",
                     f"{r.amount:,.2f}" if r.amount > 0 else "",
                     f"{r.balance:,.2f}"])
    w = -df.loc[df.amount < 0, "amount"].sum()
    d = df.loc[df.amount > 0, "amount"].sum()
    data.append(["TOTAL", "", f"{w:,.2f}", f"{d:,.2f}", ""])

    table = Table(data, colWidths=[3 * cm, 9 * cm, 3.5 * cm, 3.5 * cm, 4 * cm], repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
    SimpleDocTemplate(str(out_path), pagesize=landscape(A4), encrypt=password).build([table])


if __name__ == "__main__":
    out = Path(__file__).parent / "bank_statement.pdf"
    make_bank_pdf(out)
    print("wrote", out.name, "->", len(load_file(out)), "rows")