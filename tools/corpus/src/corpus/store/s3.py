"""S3Store — `ArtifactStore` backed by Amazon S3 (or any S3-compatible service).

Opt-in: requires the `[s3]` extra (`boto3`). Imports lazily so the base install
doesn't need it.

Layout: object key == `<prefix?><shard>/<id>.<ext>` under the configured bucket.
Local layout under `artifacts/<shard>/<id>.<ext>` is unchanged.

Authentication uses boto3's default credential chain (env vars, AWS config files,
EC2/Container metadata, etc.).
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

from corpus import paths
from corpus.store._errors import classify_remote_error

log = logging.getLogger(__name__)


def _lazy_import():
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as e:
        raise ImportError(
            "S3 backend requires the `[s3]` extra. Install with: "
            "uv pip install 'ath-corpus[s3]'"
        ) from e
    return boto3, ClientError


class S3Store:
    def __init__(
        self,
        corpus_root: Path,
        *,
        bucket: str,
        prefix: str = "",
        region: str | None = None,
    ):
        if not bucket:
            raise ValueError("S3Store requires a non-empty bucket")
        self._root = corpus_root
        self._bucket = bucket
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._region = region
        self._client = None  # lazy-init

    @property
    def root(self) -> Path:
        return self._root

    # ---- ArtifactStore Protocol ---- #

    def local_path(self, record_id: str, ext: str) -> Path:
        return paths.artifact_path(self._root, record_id, ext)

    def is_local(self, record_id: str, ext: str) -> bool:
        return self.local_path(record_id, ext).is_file()

    def exists(self, record_id: str, ext: str) -> bool:
        if self.is_local(record_id, ext):
            return True
        return self._remote_exists(self._object_key(record_id, ext))

    def ensure_local(self, record_id: str, ext: str) -> Path:
        from . import ArtifactMissing

        dst = self.local_path(record_id, ext)
        if dst.is_file():
            return dst
        key = self._object_key(record_id, ext)
        sys.stderr.write(f"[hydrate] s3://{self._bucket}/{key}\n")
        try:
            self._download(key, dst)
        except _RemoteNotFound as e:
            raise ArtifactMissing(
                f"artifact {key} missing locally and absent from "
                f"s3://{self._bucket}; re-capture required."
            ) from e
        return dst

    def put(self, record_id: str, ext: str, src: Path) -> None:
        dst = paths.ensure_parent(self.local_path(record_id, ext))
        shutil.copyfile(src, dst)
        self._upload(dst, self._object_key(record_id, ext))

    def list_local(self) -> set[str]:
        artifacts_root = self._root / "artifacts"
        if not artifacts_root.is_dir():
            return set()
        out: set[str] = set()
        for shard_dir in artifacts_root.iterdir():
            if not shard_dir.is_dir() or len(shard_dir.name) != paths.SHARD_LEN:
                continue
            for f in shard_dir.iterdir():
                if f.is_file():
                    out.add(f"{shard_dir.name}/{f.name}")
        return out

    def list_remote(self) -> set[str]:
        client = self._s3()
        names: set[str] = set()
        kwargs = {"Bucket": self._bucket}
        if self._prefix:
            kwargs["Prefix"] = self._prefix
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(**kwargs):
            for obj in page.get("Contents") or []:
                key = obj["Key"]
                if self._prefix and key.startswith(self._prefix):
                    key = key[len(self._prefix) :]
                names.add(key)
        return names

    # ---- internals ---- #

    def _object_key(self, record_id: str, ext: str) -> str:
        e = ext.lstrip(".")
        return f"{self._prefix}{paths.shard(record_id)}/{record_id}.{e}"

    def _s3(self):
        if self._client is None:
            boto3, _ = _lazy_import()
            kwargs = {}
            if self._region:
                kwargs["region_name"] = self._region
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def _remote_exists(self, key: str) -> bool:
        # `self._s3()` is called outside the try so a missing `[s3]` extra raises ImportError
        # loudly. The presence check itself never raises — operational errors (network,
        # throttle, auth) and access-denied alike collapse to "not available", matching
        # AzureBlobStore and LocalArtifactStore (exists() is total across backends).
        client = self._s3()
        try:
            client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as e:
            log.debug("s3 exists() failed for %s: %s", key, e)
            return False

    def _download(self, key: str, dst: Path) -> None:
        client = self._s3()
        _, ClientError = _lazy_import()
        paths.ensure_parent(dst)
        try:
            client.download_file(self._bucket, key, str(dst))
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            kind = classify_remote_error(code)
            if kind == "missing":
                raise _RemoteNotFound(str(e)) from e
            if kind == "denied":
                # Under a restrictive IAM policy S3 returns 403 for a *missing* key, so a
                # denial is ambiguous — surface ArtifactMissing with an actionable hint
                # rather than a raw botocore traceback.
                raise _RemoteNotFound(
                    f"{key}: access denied ({code}) — object may be absent, or the IAM "
                    f"principal lacks s3:GetObject / s3:ListBucket on the bucket."
                ) from e
            raise

    def _upload(self, src: Path, key: str) -> None:
        self._s3().upload_file(str(src), self._bucket, key)


class _RemoteNotFound(Exception):
    """Internal: object store reported the requested key as missing."""
