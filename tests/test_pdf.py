import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data" / "synthetic"))

import pytest
from reportlab.pdfgen import canvas

from core.clean import clean_description
from core.ingest import load_file, reconcile_balance
from make_pdf import make_bank_pdf

DIR = ROOT / "data" / "synthetic"


def test_pdf_matches_xlsx(tmp_path):
    p = tmp_path / "s.pdf"
    make_bank_pdf(p)
    pdf, xl = load_file(p), load_file(DIR / "bank_statement.xlsx")
    assert len(pdf) == 108
    assert pdf["date"].tolist() == xl["date"].tolist()
    assert pdf["amount"].round(2).tolist() == xl["amount"].round(2).tolist()
    assert pdf["balance"].round(2).tolist() == xl["balance"].round(2).tolist()
    assert clean_description(pdf["description"]).tolist() == clean_description(xl["description"]).tolist()


def test_pdf_balance_reconciles(tmp_path):
    p = tmp_path / "s.pdf"
    make_bank_pdf(p)
    ok, bad = reconcile_balance(load_file(p))
    assert ok, bad


def test_password_pdf_gives_clear_message(tmp_path):
    p = tmp_path / "locked.pdf"
    make_bank_pdf(p, password="secret")
    with pytest.raises(ValueError, match="password"):
        load_file(p)


def test_scanned_pdf_rejected(tmp_path):
    p = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(p))
    c.rect(50, 50, 200, 200)                 # a drawing, no text at all
    c.save()
    with pytest.raises(ValueError, match="scanned"):
        load_file(p)


def test_unsupported_layout_rejected(tmp_path):
    p = tmp_path / "text.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(100, 700, "This is a letter, not a statement table")
    c.save()
    with pytest.raises(ValueError, match="not supported"):
        load_file(p)