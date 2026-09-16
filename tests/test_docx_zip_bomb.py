"""
Regression and security test suite for DOCX zip-bomb defense and zip safety guards.
"""

import io
import os
import zipfile
import pytest
from pathlib import Path

from agents.zip_safety import (
    assert_zip_entry_is_safe,
    MAX_ENTRY_UNCOMPRESSED_BYTES,
    MAX_COMPRESSION_RATIO
)
from agents.document_parser import extract_text, _extract_docx


def create_mock_docx_zip(document_xml_content: bytes, compress_type=zipfile.ZIP_DEFLATED) -> bytes:
    """Helper to build an in-memory .docx zip package."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compress_type) as z:
        z.writestr("[Content_Types].xml", b'<?xml version="1.0"?><Types></Types>')
        z.writestr("word/document.xml", document_xml_content)
    return buf.getvalue()


def test_zip_entry_safe_check():
    """Verify assert_zip_entry_is_safe allows standard entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"<w:document><w:p><w:r><w:t>Hello world</w:t></w:r></w:p></w:document>")
    
    with zipfile.ZipFile(io.BytesIO(buf.getvalue()), "r") as z:
        info = z.getinfo("word/document.xml")
        # Should not raise
        assert_zip_entry_is_safe(info)


def test_zip_bomb_excessive_compression_ratio_rejected(tmp_path):
    """
    Constructs a small zip with an excessive compression ratio (> 100x)
    and verifies it is rejected before reading word/document.xml.
    """
    # 2MB of repetitive text compresses to ~2KB (> 1000x ratio)
    repetitive_content = b"<w:document>" + (b"<w:p><w:r><w:t>" + b"A" * 1000 + b"</w:t></w:r></w:p>") * 2000 + b"</w:document>"
    docx_bytes = create_mock_docx_zip(repetitive_content)
    
    bomb_path = tmp_path / "malicious_bomb.docx"
    bomb_path.write_bytes(docx_bytes)

    with zipfile.ZipFile(bomb_path, "r") as z:
        info = z.getinfo("word/document.xml")
        ratio = info.file_size / max(info.compress_size, 1)
        assert ratio > MAX_COMPRESSION_RATIO, f"Test setup ratio was {ratio}x"
        
        with pytest.raises(ValueError, match="excessive compression ratio"):
            assert_zip_entry_is_safe(info)

    # Calling extract_text / _extract_docx must reject it cleanly with ValueError
    with pytest.raises(ValueError, match="excessive compression ratio|possible zip-bomb"):
        _extract_docx(bomb_path)


def test_zip_bomb_oversized_uncompressed_entry_rejected(tmp_path):
    """Verifies that an entry exceeding MAX_ENTRY_UNCOMPRESSED_BYTES is rejected."""
    buf = io.BytesIO()
    # Create fake ZipInfo with file_size > MAX_ENTRY_UNCOMPRESSED_BYTES
    fake_info = zipfile.ZipInfo("word/document.xml")
    fake_info.file_size = MAX_ENTRY_UNCOMPRESSED_BYTES + 1024
    fake_info.compress_size = MAX_ENTRY_UNCOMPRESSED_BYTES  # normal ratio

    with pytest.raises(ValueError, match="exceeds maximum allowed"):
        assert_zip_entry_is_safe(fake_info)


def test_normal_legitimate_docx_parses(tmp_path):
    """Verifies that normal legitimate .docx parses without error."""
    valid_xml = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:body><w:p><w:r><w:t>Candidate: Alice Doe</w:t></w:r></w:p>'
        b'<w:p><w:r><w:t>Experience: 8 years Python distributed systems</w:t></w:r></w:p>'
        b'</w:body></w:document>'
    )
    docx_bytes = create_mock_docx_zip(valid_xml)
    doc_path = tmp_path / "valid_resume.docx"
    doc_path.write_bytes(docx_bytes)

    text = extract_text(doc_path)
    assert "Alice Doe" in text
    assert "Python distributed systems" in text
