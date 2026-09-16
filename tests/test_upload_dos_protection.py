"""
Tests for DoS, zip-bomb, and unbounded request upload protections.
Validates:
1. HTTP 413 rejection when Content-Length exceeds the maximum request body limit (50MB).
2. Early rejection of zip-bomb archives with excessive compression ratio (>100x).
3. Rejection of archives with too many entries (>500) or oversized files (>25MB).
"""

import io
import zipfile
import pytest
from fastapi.testclient import TestClient

from ui.server import app, MAX_UPLOAD_SIZE_BYTES
from agents.bulk_ingestion import BULK_ENGINE

client = TestClient(app)


def test_oversized_upload_rejected_with_413():
    """Upload exceeding MAX_UPLOAD_SIZE_BYTES (50MB) must be rejected with HTTP 413."""
    # Send request with oversized Content-Length header
    oversized_bytes = MAX_UPLOAD_SIZE_BYTES + 1024
    headers = {
        "Content-Length": str(oversized_bytes),
        "Content-Type": "multipart/form-data; boundary=----WebKitFormBoundaryX"
    }
    resp = client.post("/api/candidate/upload", headers=headers, content=b"")
    assert resp.status_code == 413
    assert "Payload Too Large" in resp.text


def test_zip_bomb_high_compression_ratio_rejected():
    """Crafted zip archive with compression ratio > 100x must be rejected before decompression."""
    zip_buffer = io.BytesIO()
    # 2MB of repeated zeros compresses to < 2KB (ratio > 1000x)
    uncompressed_data = b"0" * (2 * 1024 * 1024)
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("huge_zeroes.txt", uncompressed_data)

    zip_bytes = zip_buffer.getvalue()
    compress_size = len(zip_bytes)
    assert compress_size < 10000  # Extremely small compressed size

    batch = BULK_ENGINE.process_archive(
        zip_bytes=zip_bytes,
        batch_id="test_zip_bomb_batch",
        target_role="Software Engineer",
        uploads_root="uploads",
        cases_dir="eval_cases",
        pipeline=None,
        all_cases_list=None,
    )

    assert batch.status == "failed"
    assert any("zip-bomb" in err.lower() or "compression ratio" in err.lower() for err in batch.errors)


def test_zip_with_excessive_entries_rejected():
    """ZIP archive containing > 500 entries must be rejected immediately."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_STORED) as z:
        for i in range(505):
            z.writestr(f"file_{i}.txt", b"short content")

    batch = BULK_ENGINE.process_archive(
        zip_bytes=zip_buffer.getvalue(),
        batch_id="test_excess_entries_batch",
        target_role="Software Engineer",
        uploads_root="uploads",
        cases_dir="eval_cases",
        pipeline=None,
        all_cases_list=None,
    )

    assert batch.status == "failed"
    assert any("exceeding maximum allowed limit" in err for err in batch.errors)


def test_zip_entry_exceeding_single_file_cap_rejected():
    """ZIP archive containing single entry > 25MB uncompressed must be rejected."""
    zip_buffer = io.BytesIO()
    # 26MB uncompressed data
    data = b"x" * (26 * 1024 * 1024)
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_STORED) as z:
        z.writestr("oversized.txt", data)

    batch = BULK_ENGINE.process_archive(
        zip_bytes=zip_buffer.getvalue(),
        batch_id="test_oversized_entry_batch",
        target_role="Software Engineer",
        uploads_root="uploads",
        cases_dir="eval_cases",
        pipeline=None,
        all_cases_list=None,
    )

    assert batch.status == "failed"
    assert any("exceeds maximum allowed" in err for err in batch.errors)
