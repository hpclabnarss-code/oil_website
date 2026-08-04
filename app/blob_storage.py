"""
Vercel Blob storage helpers – works with automatically linked stores.
"""
import os
import requests
import vercel_blob


class BlobStorageError(Exception):
    pass


def _ensure_blob_env():
    """
    Ensure the required environment variables are set for the SDK.
    It checks both standard and automatically prefixed variable names.
    """
    store_id = os.environ.get("BLOB_STORE_ID") or os.environ.get("BLOB_WEBHOOK_PUBLIC_KEY_STORE_ID")
    token = os.environ.get("BLOB_READ_WRITE_TOKEN") or os.environ.get("BLOB_WEBHOOK_PUBLIC_KEY_READ_WRITE_TOKEN")

    if not store_id or not token:
        raise BlobStorageError(
            "Missing Blob credentials. Neither BLOB_STORE_ID/BLOB_READ_WRITE_TOKEN "
            "nor BLOB_WEBHOOK_PUBLIC_KEY_STORE_ID/BLOB_WEBHOOK_PUBLIC_KEY_READ_WRITE_TOKEN are set."
        )

    # Set them so the SDK can find them
    os.environ["BLOB_STORE_ID"] = store_id
    os.environ["BLOB_READ_WRITE_TOKEN"] = token


def upload_zip(pathname: str, data: bytes) -> str:
    _ensure_blob_env()
    try:
        # No extra options – the SDK reads BLOB_STORE_ID from env
        result = vercel_blob.put(
            pathname,
            data,
            {
                "addRandomSuffix": "true",
                "contentType": "application/zip",
                # "access" omitted – defaults to public for a public store
            }
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
    # Public blobs don't need auth
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise BlobStorageError(f"Could not fetch file from Vercel Blob: {e}")
    return resp.content