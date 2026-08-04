"""
Vercel Blob storage using the raw HTTP API (public store).
"""
import os
import requests


class BlobStorageError(Exception):
    pass


def _get_credentials():
    """Get store ID and token from environment (supports automatic naming)."""
    store_id = os.environ.get("BLOB_STORE_ID") or os.environ.get("BLOB_WEBHOOK_PUBLIC_KEY_STORE_ID")
    token = os.environ.get("BLOB_READ_WRITE_TOKEN") or os.environ.get("BLOB_WEBHOOK_PUBLIC_KEY_READ_WRITE_TOKEN")
    return store_id, token


def upload_zip(pathname: str, data: bytes) -> str:
    store_id, token = _get_credentials()
    if not store_id or not token:
        raise BlobStorageError("Missing Blob credentials in environment.")

    # Vercel Blob API: PUT to /{pathname} with query param for random suffix
    url = f"https://blob.vercel-storage.com/{pathname}?addRandomSuffix=true"
    headers = {
        "Authorization": f"Bearer {token}",
        "x-blob-store-id": store_id,
        "Content-Type": "application/zip",
    }

    try:
        resp = requests.put(url, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        # The API returns a JSON with the blob URL
        result = resp.json()
        blob_url = result.get("url")
        if not blob_url:
            raise BlobStorageError("No URL returned from Blob API")
        return blob_url
    except requests.RequestException as e:
        # Log the response body for debugging
        error_detail = ""
        if e.response:
            error_detail = f" (status {e.response.status_code}): {e.response.text}"
        raise BlobStorageError(f"Could not upload to Vercel Blob: {e}{error_detail}")


def delete_zip(url: str) -> None:
    store_id, token = _get_credentials()
    if not token:
        return
    try:
        # DELETE the blob using its URL (requires token)
        resp = requests.delete(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        # Ignore failures
    except Exception:
        pass


def fetch_zip_bytes(url: str) -> bytes:
    # Public store – no auth required
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as e:
        raise BlobStorageError(f"Could not fetch file: {e}")