"""
Tests for PDF parsing page ceilings, wall-clock timeouts, and HTTP 422 sync path error handling.
"""

import os
import time
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from agents.document_parser import _extract_pdf, extract_text
from ui.server import app

client = TestClient(app)


def test_pdf_page_ceiling_rejected(tmp_path, monkeypatch):
    """Verifies that a PDF exceeding HIRETRACE_MAX_PDF_PAGES is rejected before full extraction."""
    dummy_pdf = tmp_path / "oversized.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy content")

    monkeypatch.setenv("HIRETRACE_MAX_PDF_PAGES", "10")

    # Mock pypdf reader page count returning 15 pages
    class MockReader:
        pages = [object()] * 15

    with patch("pypdf.PdfReader", return_value=MockReader()):
        with pytest.raises(ValueError, match="PDF exceeds maximum page limit \\(15 > 10 pages\\)"):
            _extract_pdf(dummy_pdf)


def test_pdf_parse_timeout_rejected(tmp_path, monkeypatch):
    """Verifies that slow PDF extraction times out and instructs retry via async path."""
    dummy_pdf = tmp_path / "slow.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy content")

    monkeypatch.setenv("HIRETRACE_PDF_PARSE_TIMEOUT_SECONDS", "0.2")

    def slow_extract(*args, **kwargs):
        time.sleep(1.0)
        return "Slow text"

    # Mock pdfplumber open to hang
    class SlowPdf:
        pages = []
        def __enter__(self):
            time.sleep(1.0)
            return self
        def __exit__(self, *args):
            pass

    with patch("pypdf.PdfReader", return_value=type("R", (), {"pages": [1]})()):
        with patch("pdfplumber.open", side_effect=lambda *a, **kw: SlowPdf()):
            with pytest.raises(ValueError, match="timed out.*async \\(sync=false\\)"):
                _extract_pdf(dummy_pdf)


def test_server_sync_upload_pdf_limit_returns_422(monkeypatch):
    """
    Verifies that on the sync upload path, if PDF limit or timeout ValueError occurs,
    HTTP 422 is returned with a helpful message.
    """
    monkeypatch.setenv("HIRETRACE_DEV_MODE", "1")

    pdf_bytes = b"%PDF-1.4 mock content"

    # Mock _extract_pdf to raise the timeout ValueError
    with patch("agents.document_parser._extract_pdf", side_effect=ValueError("PDF parsing timed out after 15.0s. Please retry via the async (sync=false) path.")):
        res = client.post(
            "/api/candidate/upload?sync=true",
            data={"name": "Slow PDF Candidate", "target_role": "Backend Engineer"},
            files={"cv_file": ("resume.pdf", pdf_bytes, "application/pdf")}
        )
        assert res.status_code == 422, f"Expected 422, got {res.status_code}: {res.text}"
        assert "PDF parsing limit exceeded" in res.json().get("detail", "")
