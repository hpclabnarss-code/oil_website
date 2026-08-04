"""
Vercel Blob storage helpers for a public store – supports automatic Vercel variables.
"""
import os
import requests
import vercel_blob


class BlobStorageError(Exception):
    pass


def _get_blob_credentials():
    """Return (store_id, token) from environment, trying multiple variable names."""
    # Try the standard names first
    store_id = os.environ.get("BLOB_STORE_ID")
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")

    # If not found, try the automatic "WEBHOOK_PUBLIC_KEY" prefixed ones
    if not store_id:
        store_id = os.environ.get("BLOB_WEBHOOK_PUBLIC_KEY_STORE_ID")
    if not token:
        token = os.environ.get("BLOB_WEBHOOK_PUBLIC_KEY_READ_WRITE_TOKEN")

    return store_id, token


def upload_zip(pathname: str, data: bytes) -> str:
    store_id, token = _get_blob_credentials()
    if not token or not store_id:
        raise BlobStorageError(
            "Missing BLOB_STORE_ID or BLOB_READ_WRITE_TOKEN in environment. "
            "Please set them manually or ensure your Blob store is correctly linked."
        )

    # Explicitly set the store ID in the SDK options (some versions require this)
    try:
        result = vercel_blob.put(
            pathname,
            data,
            {
                "addRandomSuffix": "true",
                "contentType": "application/zip",
                "storeId": store_id,       # <-- explicitly provide the store ID
                # No "access" key – defaults to public
            }
        )
    except Exception as e:
        raise BlobStorageError(f"Could not upload to Vercel Blob: {e}")

    url = result.get("url")
    if not url:
        raise BlobStorageError("Vercel Blob did not return a URL")
    return url


def delete_zip(url: str) -> None:
    store_id, token = _get_blob_credentials()
    if not token:
        return  # silently fail
    try:
        # The SDK's delete() also needs the store ID? Usually it infers from env.
        vercel_blob.delete([url])
    except Exception:
        pass


def fetch_zip_bytes(url: str) -> bytes:
    # For public blobs, no auth header is needed.
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise BlobStorageError(f"Could not fetch file from Vercel Blob: {e}")
    return resp.content