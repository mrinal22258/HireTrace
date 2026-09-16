"""
Shared ZIP Safety and Decompression Guard for HireTrace.

Provides defense-in-depth protections against zip-bombs, decompression resource exhaustion,
and excessive compression ratio attacks across bulk archives and individual .docx documents.
"""

import zipfile
from typing import Optional

# Safe limits for zip extraction
MAX_ZIP_ENTRIES: int = 500
MAX_ENTRY_UNCOMPRESSED_BYTES: int = 25 * 1024 * 1024   # 25 MB
MAX_TOTAL_UNCOMPRESSED_BYTES: int = 200 * 1024 * 1024  # 200 MB
MAX_COMPRESSION_RATIO: float = 100.0
MIN_SIZE_FOR_RATIO_CHECK: int = 10 * 1024              # 10 KB


def assert_zip_entry_is_safe(
    zip_info: zipfile.ZipInfo,
    max_uncompressed_bytes: int = MAX_ENTRY_UNCOMPRESSED_BYTES,
    max_ratio: float = MAX_COMPRESSION_RATIO,
    min_size_for_ratio_check: int = MIN_SIZE_FOR_RATIO_CHECK
) -> None:
    """
    Validates that a single zip entry does not exceed safe size or compression ratio limits.
    Raises ValueError if the entry is potentially dangerous (zip bomb).

    :param zip_info: zipfile.ZipInfo object for the entry.
    :param max_uncompressed_bytes: Maximum allowed uncompressed byte size for this entry.
    :param max_ratio: Maximum allowed compression ratio (uncompressed / compressed).
    :param min_size_for_ratio_check: Minimum uncompressed size before ratio checks trigger.
    :raises ValueError: If uncompressed size or compression ratio exceeds threshold.
    """
    if zip_info.file_size > max_uncompressed_bytes:
        raise ValueError(
            f"ZIP entry '{zip_info.filename}' uncompressed size "
            f"({zip_info.file_size / (1024 * 1024):.1f} MB) exceeds maximum allowed "
            f"{max_uncompressed_bytes / (1024 * 1024):.0f} MB."
        )

    if zip_info.file_size > min_size_for_ratio_check:
        compress_size = max(zip_info.compress_size, 1)
        ratio = zip_info.file_size / compress_size
        if ratio > max_ratio:
            raise ValueError(
                f"ZIP entry '{zip_info.filename}' has excessive compression ratio "
                f"({ratio:.1f}x > {max_ratio:.0f}x), possible zip-bomb."
            )
