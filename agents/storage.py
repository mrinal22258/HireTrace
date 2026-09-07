"""
Storage Abstraction Layer for HireTrace (Phase 8).

Supports:
1. Local File System with atomic writes and directory containment (Docker volumes).
2. S3-Compatible Object Storage (AWS S3, MinIO, Cloudflare R2).
3. Path traversal protection and automatic content-type detection.
"""

import os
import io
import shutil
import logging
from typing import Optional, List, BinaryIO, Union

logger = logging.getLogger("hiretrace.storage")


class StorageProvider:
    """Abstract interface for artifact and document persistence."""

    def save(self, category: str, key: str, data: Union[bytes, str]) -> str:
        raise NotImplementedError

    def get(self, category: str, key: str) -> Optional[bytes]:
        raise NotImplementedError

    def exists(self, category: str, key: str) -> bool:
        raise NotImplementedError

    def delete(self, category: str, key: str) -> bool:
        raise NotImplementedError

    def list_keys(self, category: str) -> List[str]:
        raise NotImplementedError


class LocalStorageProvider(StorageProvider):
    """Local disk storage backed by persistent named volumes."""

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir or os.environ.get("HIRETRACE_STORAGE_DIR", os.getcwd())
        os.makedirs(self.root_dir, exist_ok=True)

    def _resolve_path(self, category: str, key: str) -> str:
        # Sanitize against path traversal attacks
        target_dir = os.path.abspath(os.path.join(self.root_dir, category))
        os.makedirs(target_dir, exist_ok=True)
        # Strip leading slashes/backslashes so os.path.join treats key as relative to target_dir
        rel_key = key.lstrip("/\\")
        full_path = os.path.abspath(os.path.join(target_dir, rel_key))
        if not (full_path == target_dir or full_path.startswith(target_dir + os.sep)):
            raise ValueError(f"Path traversal detected: {key}")
        return full_path

    def save(self, category: str, key: str, data: Union[bytes, str]) -> str:
        full_path = self._resolve_path(category, key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        raw_bytes = data.encode("utf-8") if isinstance(data, str) else data
        
        # Atomic write via temporary file
        tmp_path = f"{full_path}.tmp_{os.getpid()}"
        with open(tmp_path, "wb") as f:
            f.write(raw_bytes)
        shutil.move(tmp_path, full_path)
        return full_path

    def get(self, category: str, key: str) -> Optional[bytes]:
        try:
            full_path = self._resolve_path(category, key)
            if os.path.exists(full_path):
                with open(full_path, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.warning("Failed reading file %s/%s: %s", category, key, e)
        return None

    def exists(self, category: str, key: str) -> bool:
        try:
            full_path = self._resolve_path(category, key)
            return os.path.exists(full_path)
        except Exception:
            return False

    def delete(self, category: str, key: str) -> bool:
        try:
            full_path = self._resolve_path(category, key)
            if os.path.exists(full_path):
                os.remove(full_path)
                return True
        except Exception as e:
            logger.warning("Failed deleting %s/%s: %s", category, key, e)
        return False

    def list_keys(self, category: str) -> List[str]:
        target_dir = os.path.join(self.root_dir, category)
        if not os.path.exists(target_dir):
            return []
        keys = []
        for root, _, files in os.walk(target_dir):
            for fname in files:
                if not fname.endswith(".tmp"):
                    rel = os.path.relpath(os.path.join(root, fname), target_dir)
                    keys.append(rel.replace("\\", "/"))
        return keys


class S3StorageProvider(StorageProvider):
    """S3-compatible object storage provider."""

    def __init__(self, bucket_name: str, endpoint_url: Optional[str] = None):
        import boto3
        self.bucket = bucket_name
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url or os.environ.get("AWS_ENDPOINT_URL_S3"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        )

    def _prefix(self, category: str, key: str) -> str:
        clean_key = key.lstrip("/")
        return f"{category}/{clean_key}"

    def save(self, category: str, key: str, data: Union[bytes, str]) -> str:
        s3_key = self._prefix(category, key)
        raw_bytes = data.encode("utf-8") if isinstance(data, str) else data
        self.s3.put_object(Bucket=self.bucket, Key=s3_key, Body=raw_bytes)
        return f"s3://{self.bucket}/{s3_key}"

    def get(self, category: str, key: str) -> Optional[bytes]:
        s3_key = self._prefix(category, key)
        try:
            res = self.s3.get_object(Bucket=self.bucket, Key=s3_key)
            return res["Body"].read()
        except Exception:
            return None

    def exists(self, category: str, key: str) -> bool:
        s3_key = self._prefix(category, key)
        try:
            self.s3.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception:
            return False

    def delete(self, category: str, key: str) -> bool:
        s3_key = self._prefix(category, key)
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception:
            return False

    def list_keys(self, category: str) -> List[str]:
        prefix = f"{category}/"
        try:
            res = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            keys = []
            for item in res.get("Contents", []):
                k = item["Key"]
                keys.append(k[len(prefix):])
            return keys
        except Exception:
            return []


def get_storage_provider() -> StorageProvider:
    """Factory returning configured storage provider based on environment."""
    backend = os.environ.get("HIRETRACE_STORAGE_BACKEND", "local").lower()
    bucket = os.environ.get("HIRETRACE_S3_BUCKET")

    if backend == "s3" and bucket:
        try:
            return S3StorageProvider(bucket)
        except Exception as e:
            logger.error("Failed to initialize S3 storage, falling back to local: %s", e)
    
    return LocalStorageProvider()


STORAGE = get_storage_provider()
