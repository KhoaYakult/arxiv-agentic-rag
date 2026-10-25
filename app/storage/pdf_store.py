"""
app/storage/pdf_store.py
=========================
Luu PDF goc cua paper vao Supabase Storage (bucket private) de web UI hien PDF canh
cuoc hoi thoai. Vi sao can: /tmp tren Vercel bi xoa khi instance khoi dong lai, va
Vercel cat response > 4.5 MB nen PDF khong the di qua API - trinh duyet tai thang
tu Storage bang signed URL (het han sau SIGNED_URL_TTL giay).

Goi Storage REST API bang httpx (da co san), khong them SDK. Tat ca loi -> StorageError;
noi goi quyet dinh co nuot loi hay khong (job index: nuot, chi WARN).
"""

import httpx

from app.config import settings

SIGNED_URL_TTL = 3600

# Test gan httpx.MockTransport vao day; None = mang that.
_transport: httpx.AsyncBaseTransport | None = None


class StorageError(Exception):
    """Loi khi goi Supabase Storage (HTTP loi, thieu truong trong response...)."""


def is_enabled() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _object_path(paper_id: str) -> str:
    return f"{settings.storage_bucket}/{paper_id}.pdf"


def _base_url() -> str:
    return f"{settings.supabase_url.rstrip('/')}/storage/v1"


def _client() -> httpx.AsyncClient:
    key = settings.supabase_service_role_key
    return httpx.AsyncClient(
        base_url=_base_url(),
        headers={"Authorization": f"Bearer {key}", "apikey": key},
        timeout=30,
        transport=_transport,
    )


async def upload_pdf(paper_id: str, content: bytes) -> None:
    """Ghi (de neu da co) object <bucket>/<paper_id>.pdf."""
    try:
        async with _client() as client:
            r = await client.post(
                f"/object/{_object_path(paper_id)}",
                content=content,
                headers={"Content-Type": "application/pdf", "x-upsert": "true"},
            )
    except httpx.HTTPError as e:
        raise StorageError(f"upload {paper_id}: {type(e).__name__}") from e
    if r.status_code >= 300:
        raise StorageError(f"upload {paper_id}: HTTP {r.status_code} {r.text[:200]}")


async def signed_url(paper_id: str, expires_in: int = SIGNED_URL_TTL) -> str:
    """URL tuyet doi, ai co URL deu tai duoc PDF cho toi khi het han."""
    try:
        async with _client() as client:
            r = await client.post(f"/object/sign/{_object_path(paper_id)}", json={"expiresIn": expires_in})
    except httpx.HTTPError as e:
        raise StorageError(f"sign {paper_id}: {type(e).__name__}") from e
    if r.status_code >= 300:
        raise StorageError(f"sign {paper_id}: HTTP {r.status_code} {r.text[:200]}")
    try:
        body = r.json()
    except ValueError as e:
        raise StorageError(f"sign {paper_id}: response khong phai JSON") from e
    if not isinstance(body, dict):
        raise StorageError(f"sign {paper_id}: response khong phai object JSON")
    signed = body.get("signedURL") or body.get("signedUrl")
    if not isinstance(signed, str) or not signed:
        raise StorageError(f"sign {paper_id}: response thieu signedURL")
    return f"{_base_url()}{signed}"


async def delete_pdf(paper_id: str) -> None:
    """Xoa object; object khong ton tai (404) khong phai loi."""
    try:
        async with _client() as client:
            r = await client.delete(f"/object/{_object_path(paper_id)}")
    except httpx.HTTPError as e:
        raise StorageError(f"delete {paper_id}: {type(e).__name__}") from e
    if r.status_code >= 300 and r.status_code != 404:
        raise StorageError(f"delete {paper_id}: HTTP {r.status_code} {r.text[:200]}")
