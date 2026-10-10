"""StorageProvider: where crop photos live (ADR-0008), behind an interface so moving to another object
store later (Cloudflare R2 is the sanctioned alternative) is one new class.

The Supabase implementation calls the Storage REST API WITH THE CALLER'S OWN JWT, so the bucket's
row-level policy (supabase/migrations/20261010120000_disease_scans.sql) decides who may read, write or
delete: the API never holds a key that can bypass it. Only the re-encoded, EXIF-free JPEG is ever stored.

Methods raise `StorageError` for anything that is not success. Callers treat storage as best effort for
saving a scan (the diagnosis does not depend on it) and as required only for deletion.
"""
from abc import ABC, abstractmethod

import httpx


class StorageError(Exception):
    """A storage call failed. The message holds a status code or a reason, never a token or a URL with one."""


def _body_status(response: httpx.Response) -> str | None:
    try:
        value = response.json().get("statusCode")
    except (ValueError, AttributeError):
        return None
    return str(value) if value is not None else None


class StorageProvider(ABC):
    @abstractmethod
    async def put(self, key: str, data: bytes, *, content_type: str, token: str) -> None: ...

    @abstractmethod
    async def delete(self, key: str, *, token: str) -> None: ...

    @abstractmethod
    async def signed_url(self, key: str, *, token: str, expires_in: int = 3600) -> str: ...


class SupabaseStorage(StorageProvider):
    def __init__(self, base_url: str, anon_key: str, bucket: str, *, client: httpx.AsyncClient | None = None):
        self._base = base_url.rstrip("/") + "/storage/v1"
        self._anon = anon_key
        self._bucket = bucket
        self._client = client  # tests pass one; production creates a short-lived client per call

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "apikey": self._anon}

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            if self._client is not None:
                return await self._client.request(method, url, timeout=15.0, **kwargs)
            async with httpx.AsyncClient(timeout=15.0) as client:
                return await client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise StorageError(f"storage unreachable ({type(exc).__name__})") from exc

    async def put(self, key: str, data: bytes, *, content_type: str, token: str) -> None:
        response = await self._send(
            "POST",
            f"{self._base}/object/{self._bucket}/{key}",
            headers={**self._headers(token), "Content-Type": content_type, "x-upsert": "false"},
            content=data,
        )
        if response.status_code not in (200, 201):
            raise StorageError(f"upload failed ({response.status_code})")

    async def delete(self, key: str, *, token: str) -> None:
        response = await self._send(
            "DELETE", f"{self._base}/object/{self._bucket}/{key}", headers=self._headers(token)
        )
        # An object that is not there is not an error here (the caller deletes its row either way). Access
        # denied by row-level security IS an error. Supabase Storage reports its own error code in the JSON
        # body (`statusCode`) and often wraps it in an HTTP 400, so the body is read, not just the status.
        if response.status_code in (200, 204, 404) or _body_status(response) == "404":
            return
        raise StorageError(f"delete failed ({response.status_code})")

    async def signed_url(self, key: str, *, token: str, expires_in: int = 3600) -> str:
        response = await self._send(
            "POST",
            f"{self._base}/object/sign/{self._bucket}/{key}",
            headers={**self._headers(token), "Content-Type": "application/json"},
            json={"expiresIn": expires_in},
        )
        if response.status_code != 200:
            raise StorageError(f"signing failed ({response.status_code})")
        signed = response.json().get("signedURL")
        if not isinstance(signed, str) or not signed:
            raise StorageError("signing returned no URL")
        return f"{self._base}{signed}"
