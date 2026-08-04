"""
Vercel Blob storage helpers for a public store.
"""
import os
import requests
import vercel_blob


class BlobStorageError(Exception):
    pass


def upload_zip(pathname: str, data: bytes) -> str:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise BlobStorageError("BLOB_READ_WRITE_TOKEN not set in environment")

    try:
        result = vercel_blob.put(
            pathname,
            data,
            {
                "addRandomSuffix": "true",
                "contentType": "application/zip",
                # No "access" – defaults to public (or you can add "access": "public")
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
    # For public blobs, no auth header is needed.
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise BlobStorageError(f"Could not fetch file from Vercel Blob: {e}")
    return resp.content