"""
Vercel Blob storage helpers using direct HTTP API (supports private stores).
"""
import os
import requests


class BlobStorageError(Exception):
    pass


def upload_zip(pathname: str, data: bytes) -> str:
    """Uploads zip bytes to Vercel Blob (private store) and returns the URL."""
    store_id = os.environ.get("BLOB_STORE_ID")
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not store_id or not token:
        raise BlobStorageError("Missing BLOB_STORE_ID or BLOB_READ_WRITE_TOKEN")

    # Vercel Blob HTTP API endpoint
    api_url = "https://blob.vercel-storage.com/v1/blobs/upload"

    params = {
        "storeId": store_id,
        "access": "private",           # critical for private store
        "pathname": pathname,
        "addRandomSuffix": "true",
        "contentType": "application/zip",
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/zip",
    }

    try:
        resp = requests.post(api_url, params=params, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise BlobStorageError(f"Could not upload to Vercel Blob: {e}")

    result = resp.json()
    blob_url = result.get("url")
    if not blob_url:
        raise BlobStorageError("Vercel Blob did not return a URL")
    return blob_url


def delete_zip(url: str) -> None:
    """Deletes a blob by URL using the Vercel Blob delete API."""
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        return  # silently fail, as before
    try:
        # Use the Vercel Blob delete API
        resp = requests.delete(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        # We ignore failures
    except Exception:
        pass


def fetch_zip_bytes(url: str) -> bytes:
    """Fetches a private blob's raw bytes using the read token."""
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
        raise BlobStorageError(f"Could not fetch file from Vercel Blob: {e}")
    return resp.content