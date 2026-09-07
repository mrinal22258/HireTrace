"""
Phase 8 Durability & Storage Test Suite
Tests storage provider persistence, atomic writes, path traversal prevention, and Alembic migrations.
"""

import os
import shutil
import tempfile
import pytest
from agents.storage import LocalStorageProvider, get_storage_provider


def test_local_storage_atomic_save_and_retrieve():
    """Test LocalStorageProvider atomic file writes and retrieval."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalStorageProvider(root_dir=temp_dir)

        category = "test_uploads"
        key = "candidate_123/cv.txt"
        content = "Sample CV contents for candidate 123"

        saved_path = storage.save(category, key, content)
        assert os.path.exists(saved_path)
        assert storage.exists(category, key)

        retrieved_bytes = storage.get(category, key)
        assert retrieved_bytes is not None
        assert retrieved_bytes.decode("utf-8") == content

        # Verify listing
        keys = storage.list_keys(category)
        assert any("candidate_123/cv.txt" in k or "candidate_123\\cv.txt" in k for k in keys)

        # Verify delete
        deleted = storage.delete(category, key)
        assert deleted is True
        assert not storage.exists(category, key)


def test_local_storage_path_traversal_prevention():
    """Verify that malicious relative paths outside category directory are rejected."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalStorageProvider(root_dir=temp_dir)
        category = "safe_category"

        # Path traversal attempt
        with pytest.raises(ValueError, match="Path traversal detected"):
            storage.save(category, "../../etc/passwd", "evil data")


def test_alembic_upgrade_and_downgrade():
    """Verify that Alembic migrations apply cleanly and can be inspected."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")

    # Run check / upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify downgrade and re-upgrade
    command.downgrade(alembic_cfg, "-1")
    command.upgrade(alembic_cfg, "head")
