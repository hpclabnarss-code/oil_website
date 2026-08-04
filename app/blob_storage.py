"""
Vercel Blob storage helpers using the official Python SDK (public store).
"""
import os
import requests
import vercel_blob


class BlobStorageError(Exception):
    pass


def upload_zip(pathname: str, data: bytes) -> str:
    """Uploads zip bytes to Vercel Blob (public store) and returns the URL."""
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise BlobStorageError("BLOB_READ_WRITE_TOKEN not set in environment")

    try:
        # No "access" key – defaults to public, which matches the store
        result = vercel_blob.put(
            pathname,
            data,
            {
                "addRandomSuffix": "true",
                "contentType": "application/zip",
                # "access": "public" is optional, but we omit it to avoid errors
            }
        )
    except Exception as e:
        raise BlobStorageError(f"Could not upload to Vercel Blob: {e}")

    url = result.get("url")
    if not url:
        raise BlobStorageError("Vercel Blob did not return a URL")
    return url


def delete_zip(url: str) -> None:
    """Deletes a blob by URL using the SDK."""
    try:
        vercel_blob.delete([url])
    except Exception:
        pass


def fetch_zip_bytes(url: str) -> bytes:
    """Fetches a public blob's raw bytes – no auth needed."""
    # For public blobs, no Authorization header is required.
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise BlobStorageError(f"Could not fetch file from Vercel Blob: {e}")
    return resp.content