"""
Vercel Blob storage helpers for storing uploaded shapefile zips.

Vercel's serverless functions run on a read-only filesystem (only /tmp is
writable, and it is wiped between invocations / cold starts), so writing
uploaded zips to a local `uploads/` folder does not survive in production.
This module stores the zip bytes in Vercel Blob instead — durable object
storage reachable over HTTPS — using the `vercel_blob` PyPI package, which
wraps Vercel's Blob REST API.

Setup required in the Vercel dashboard (one-time):
    Project -> Storage -> Create Database -> Blob
    Connect it to this project. Vercel then auto-populates the
    BLOB_READ_WRITE_TOKEN environment variable that `vercel_blob` reads.

Note on access: Vercel Blob URLs are public-by-default (anyone with the URL
can fetch the file, there's no way to gate it with our own Bearer token at
the storage layer). To avoid handing out that raw URL, our own
/api/admin/spills/{id}/download endpoint stays behind admin auth and
fetches+streams the bytes server-side rather than redirecting the client
to the blob URL directly.
"""
import os
import requests
import vercel_blob


class BlobStorageError(Exception):
    """Raised when an upload/delete/fetch against Vercel Blob fails."""
    pass


def upload_zip(pathname: str, data: bytes) -> str:
    """Uploads zip bytes to Vercel Blob and returns the public URL."""
    try:
        result = vercel_blob.put(
            pathname,
            data,
            {
                "addRandomSuffix": "true",
                "contentType": "application/zip",
                "access": "private",          # <-- crucial for private stores
            },
        )
    except Exception as e:
        raise BlobStorageError(f"Could not upload to Vercel Blob: {e}")
    url = result.get("url")
    if not url:
        raise BlobStorageError("Vercel Blob did not return a URL for the upload")
    return url


def delete_zip(url: str) -> None:
    """Deletes a blob by URL. Never raises — a storage delete failure
    should not block the DB record from being deleted."""
    try:
        vercel_blob.delete([url])
    except Exception:
        pass


def fetch_zip_bytes(url: str) -> bytes:
    """Fetches a blob's raw bytes so we can stream it back through our own
    authenticated endpoint instead of exposing the public blob URL."""
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise BlobStorageError("BLOB_READ_WRITE_TOKEN not set in environment")
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        raise BlobStorageError(f"Could not fetch file from Vercel Blob: {e}")
    return resp.content