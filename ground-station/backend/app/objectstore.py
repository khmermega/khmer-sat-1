"""Image object storage: local filesystem (dev) or S3-compatible MinIO (Docker)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

_KEY_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")


def _check_key(key: str) -> None:
    if not _KEY_RE.match(key) or ".." in key or key.startswith("/"):
        raise ValueError(f"invalid object key {key!r}")


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...


class LocalObjectStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        _check_key(key)
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        _check_key(key)
        return (self.root / key).read_bytes()


class S3ObjectStore:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        import boto3
        from botocore.config import Config

        if not access_key or not secret_key:
            raise ValueError("S3_ACCESS_KEY and S3_SECRET_KEY must be set for OBJECT_STORE=s3")
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
            region_name="us-east-1",
        )
        self.bucket = bucket
        try:
            self._s3.head_bucket(Bucket=bucket)
        except Exception:  # noqa: BLE001 - bucket missing -> create
            self._s3.create_bucket(Bucket=bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        _check_key(key)
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        _check_key(key)
        return self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
