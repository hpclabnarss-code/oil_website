"""
Vercel Blob storage helpers for storing uploaded shapefile zips.
"""
import os
import requests
import vercel_blob


class BlobStorageError(Exception):
    pass


def upload_zip(pathname: str, data: bytes) -> str:
    """Uploads zip bytes to Vercel Blob (private store) and returns the URL."""
    try:
        result = vercel_blob.put(
            pathname,
            data,
            addRandomSuffix=True,      # boolean, not "true"
            contentType="application/zip",
            access="private",          # crucial: matches private store
        )
    except Exception as e:
        raise BlobStorageError(f"Could not upload to Vercel Blob: {e}")
    url = result.get("url")
    if not url:
        raise BlobStorageError("Vercel Blob did not return a URL")
    return url


def delete_zip(url: str) -> None:
    try:
        vercel_blob.delete([url])
    except Exception:
        pass


def fetch_zip_bytes(url: str) -> bytes:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise BlobStorageError("BLOB_READ_WRITE_TOKEN not set")
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        raise BlobStorageError(f"Could not fetch file: {e}")
    return resp.content