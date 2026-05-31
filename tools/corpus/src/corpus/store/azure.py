"""AzureBlobStore — `ArtifactStore` backed by Azure Blob Storage.

Opt-in: requires the `[azure]` extra (`azure-storage-blob`, `azure-identity`).
Imports the SDK lazily so the base install doesn't need it.

Generalized from the reference's `az`-CLI subprocess implementation: account /
container / prefix are constructor params (no hardcoded values), authentication
uses `DefaultAzureCredential` from `azure-identity`.

Layout: blob name == `<prefix?><shard>/<id>.<ext>`. Local layout under
`artifacts/<shard>/<id>.<ext>` is unchanged.
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

from corpus import paths

log = logging.getLogger(__name__)


def _lazy_import():
    """Import the Azure SDK on demand and return the symbols we need.

    Raises ImportError with operator-actionable text when the extra isn't installed.
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as e:
        raise ImportError(
            "Azure backend requires the `[azure]` extra. Install with: "
            "uv pip install 'ath-corpus[azure]' (or pip install …)"
        ) from e
    return BlobServiceClient, DefaultAzureCredential


class AzureBlobStore:
    """Azure-Blob-backed `ArtifactStore`. Local pre-empts remote on `is_local`."""

    def __init__(
        self,
        corpus_root: Path,
        *,
        account: str,
        container: str,
        prefix: str = "",
    ):
        if not account or not container:
            raise ValueError("AzureBlobStore requires non-empty account and container")
        self._root = corpus_root
        self._account = account
        self._container = container
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._client = None  # lazy-init on first remote op

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
        return self._remote_exists(self._blob_name(record_id, ext))

    def ensure_local(self, record_id: str, ext: str) -> Path:
        from . import ArtifactMissing

        dst = self.local_path(record_id, ext)
        if dst.is_file():
            return dst
        blob_name = self._blob_name(record_id, ext)
        sys.stderr.write(f"[hydrate] {blob_name}\n")
        try:
            self._download(blob_name, dst)
        except _RemoteNotFound as e:
            raise ArtifactMissing(
                f"artifact {blob_name} missing locally and absent from "
                f"azure://{self._account}/{self._container}; re-capture required."
            ) from e
        return dst

    def put(self, record_id: str, ext: str, src: Path) -> None:
        """Persist `src` locally AND upload to the remote container.

        The local copy is the operating cache; the upload is the durable mirror.
        Idempotent: re-uploading an existing blob with identical bytes is fine.
        """
        dst = paths.ensure_parent(self.local_path(record_id, ext))
        shutil.copyfile(src, dst)
        self._upload(dst, self._blob_name(record_id, ext))

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
        client = self._container_client()
        names: set[str] = set()
        for blob in client.list_blobs(name_starts_with=self._prefix or None):
            name = blob.name
            if self._prefix and name.startswith(self._prefix):
                name = name[len(self._prefix) :]
            names.add(name)
        return names

    # ---- internals ---- #

    def _blob_name(self, record_id: str, ext: str) -> str:
        e = ext.lstrip(".")
        return f"{self._prefix}{paths.shard(record_id)}/{record_id}.{e}"

    def _container_client(self):
        if self._client is None:
            BlobServiceClient, DefaultAzureCredential = _lazy_import()
            url = f"https://{self._account}.blob.core.windows.net"
            self._client = BlobServiceClient(
                account_url=url, credential=DefaultAzureCredential()
            ).get_container_client(self._container)
        return self._client

    def _remote_exists(self, blob_name: str) -> bool:
        # ImportError (missing [azure] extra) propagates; only operational errors
        # (network, auth) are swallowed to "remote unknown".
        client = self._container_client().get_blob_client(blob_name)
        try:
            return bool(client.exists())
        except Exception as e:
            log.debug("azure exists() failed for %s: %s", blob_name, e)
            return False

    def _download(self, blob_name: str, dst: Path) -> None:
        paths.ensure_parent(dst)
        client = self._container_client().get_blob_client(blob_name)
        try:
            stream = client.download_blob()
        except Exception as e:
            # azure.core.exceptions.ResourceNotFoundError is one common path; others
            # surface as generic errors. Narrow by name string to avoid importing
            # the exceptions module just to type-test.
            if "ResourceNotFound" in type(e).__name__ or "404" in str(e):
                raise _RemoteNotFound(str(e)) from e
            raise
        with dst.open("wb") as fh:
            stream.readinto(fh)

    def _upload(self, src: Path, blob_name: str) -> None:
        client = self._container_client().get_blob_client(blob_name)
        with src.open("rb") as fh:
            client.upload_blob(fh, overwrite=True)


class _RemoteNotFound(Exception):
    """Internal: blob storage reported the requested artifact as missing."""
