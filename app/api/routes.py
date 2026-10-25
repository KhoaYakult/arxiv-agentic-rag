"""
app/api/routes.py
==================
Dinh nghia cac endpoint REST API cua ung dung.

Cac endpoint:
  GET    /health                  — Kiem tra server dang song (khong can API key)
  GET    /health/db               — SELECT 1 qua pool Postgres (khong can API key; Vercel
                                     cron goi hang ngay de Supabase free khong auto-pause)
  GET    /papers                  — Lay danh sach bai bao status='ready'
  POST   /upload                  — Upload PDF (<= max_upload_mb), index chay nen
                                     (BackgroundTasks), tra 202 (hoac 200 neu file da
                                     index truoc do - dedup sha256)
  POST   /papers/arxiv            — Import theo arXiv ID: server tu tai PDF tu arxiv.org
                                     (khong vuong gioi han body 4.5 MB cua Vercel), cung
                                     luong dedup/index nen nhu /upload
  GET    /papers/{id}/status      — Poll tien do xu ly sau /upload (job 'processing' >15
                                     phut bi danh dau 'failed')
  DELETE /papers/{id}             — Xoa paper (cascade sections/chunks/paper_cards)
  POST   /ask                     — Hoi Agent va nhan cau tra loi

Moi route tru 2 route /health* yeu cau header X-API-Key neu settings.app_api_key
khong rong (xem app/api/auth.py).

Luong xu ly /upload (Phase 2 - Postgres/Supabase):
  Request tra ve 202 NGAY sau khi luu file + tao row papers(status='processing') -
  phan cham (parse/embed/index) chay nen qua BackgroundTasks, vi Gemini
  free-tier rate-limit cooldown co the lam buoc embed mat >61s (xem
  app/indexing/embeddings.py) - block ca request se qua lau va de bi client
  timeout. Client poll GET /papers/{paper_id}/status de biet khi nao xong:
    PDF file -> (dong bo, nhanh) luu file + upsert_paper(status="processing")
             -> tra ve 202
             -> (nen) chunker.process_paper_ingestion()
             -> (nen) embeddings.get_embedding_provider().embed_documents()
             -> (nen) repository.insert_sections() + insert_chunks()
             -> (nen) set_paper_status("ready") hoac ("failed") neu loi

Event loop: parse PDF va embed_documents la ham SYNC nang (embed co the
time.sleep(61) do Gemini free-tier cooldown) - chay qua asyncio.to_thread() de
khong dong bang ca server; _index_lock cho phep moi process chi 1 job index chay
cung luc (2 job embed song song se vuot quota Gemini 100 embedding/phut).

Luong xu ly /ask:
  AskRequest -> rag_graph.ask() -> AskResponse

Phase 1 (ChromaDB + BM25 pickle, app/indexing/vector_store.py + bm25_store.py)
da bi thay the hoan toan o day va sau do xoa het khoi repo (xem
git history neu can xem lai code cu).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse

from app.api.auth import require_api_key
from app.api.schemas import (
    ArxivImportRequest,
    AskRequest,
    AskResponse,
    HealthDbResponse,
    HealthResponse,
    PaperInfo,
    PapersResponse,
    PaperStatusResponse,
    PdfUrlResponse,
    SourceChunk,
    UploadResponse,
)
from app.config import settings

# `router` la router goc (main.py include vao prefix /api/v1). /health va /health/db
# gan thang len no (cong khai); moi route con lai gan len `protected` - router con
# co dependency require_api_key, roi include vao `router`.
router = APIRouter()
protected = APIRouter(dependencies=[Depends(require_api_key)])

# ── Validate paper_id / arxiv_id ──
# paper_id do client gui duoc noi vao duong dan file (data_dir/{paper_id}.pdf) nen
# phai chan ky tu nhu "/", "\\", ".." (path traversal). Regex nay ap cho paper_id
# client tu dat luc upload.
PAPER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
# paper_id dung de TRA CUU/XOA (path param): cho phep them dau "." vi paper import
# tu arXiv co dang "arxiv-2401.15884" (do server tao, khong phai client dat). Van chan
# "/", "\\" va ".." ; chu hoa cho phep de paper cu van truy cap duoc.
LOOKUP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")

ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"
ARXIV_API_URL = "http://export.arxiv.org/api/query?id_list={arxiv_id}"
ARXIV_MAX_PDF_BYTES = 30 * 1024 * 1024
ARXIV_USER_AGENT = "arxiv-agentic-rag/1.0 (research RAG demo; paper import by arXiv ID)"

# Job 'processing' lau hon muc nay coi nhu da chet (function bi kill, process restart...)
# - khong ai con cap nhat row nua nen phai tu danh dau 'failed' o GET status.
STUCK_JOB_AFTER = timedelta(minutes=15)

# Moi process chi cho 1 job index chay cung luc: vua tranh vuot quota embed Gemini
# free-tier (100/phut) khi 2 nguoi upload dong thoi, vua tranh 2 lan parse layout
# (~500 MiB RAM moi lan) chong len nhau.
_index_lock = asyncio.Lock()


def validate_paper_id(paper_id: str) -> str:
    """paper_id do client dat (form field /upload): 400 neu khong khop PAPER_ID_RE."""
    if not PAPER_ID_RE.fullmatch(paper_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="paper_id khong hop le: chi dung chu thuong a-z, so, '-', '_' "
                   "(toi da 64 ky tu, ky tu dau phai la chu/so).",
        )
    return paper_id


def validate_lookup_id(paper_id: str) -> str:
    """paper_id trong URL (status/delete): 400 neu co ky tu nguy hiem (path traversal)."""
    if not LOOKUP_ID_RE.fullmatch(paper_id) or ".." in paper_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="paper_id khong hop le.",
        )
    return paper_id


def make_paper_id(filename: str) -> str:
    """
    paper_id mac dinh: slug cua ten file (toi da 40 ky tu) + '-' + 6 ky tu hex ngau
    nhien - 2 nguoi dung upload file cung ten (vd 'paper.pdf') KHONG dam nhau.
    Luon khop PAPER_ID_RE (slug khong rong, bat dau bang chu/so).
    """
    stem = Path(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:40].strip("-") or "paper"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def validate_arxiv_id(arxiv_id: str) -> str:
    """ArXiv ID kieu moi (YYMM.NNNN[N][vK]) - 400 neu khong khop."""
    arxiv_id = arxiv_id.strip()
    if not ARXIV_ID_RE.fullmatch(arxiv_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="arxiv_id khong hop le. Dinh dang dung: 'YYMM.NNNNN' (co the kem "
                   "phien ban 'vK'), vd '2401.15884' hoac '2401.15884v2'.",
        )
    return arxiv_id


def ensure_pdf(content: bytes, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
    """File that phai bat dau bang magic bytes '%PDF' - chi tin duoi .pdf la khong du."""
    if not content.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status_code,
            detail="Noi dung khong phai file PDF hop le (thieu header '%PDF').",
        )


def enforce_upload_limit(content: bytes, max_mb: float | None = None) -> None:
    """413 neu file vuot settings.max_upload_mb (mac dinh 4.0 - Vercel cat body o 4.5 MB)."""
    limit_mb = settings.max_upload_mb if max_mb is None else max_mb
    if len(content) > int(limit_mb * 1024 * 1024):
        raise HTTPException(
            status_code=413,
            detail=f"File vuot gioi han {limit_mb:g} MB. Voi paper tren arXiv hay dung "
                   f"POST /api/v1/papers/arxiv (server tu tai PDF, khong gioi han nay).",
        )


def is_quota_error(exc: BaseException) -> bool:
    """True neu loi den tu het quota/rate limit cua nha cung cap AI (Gemini embed, Groq...).
    LangChain hay boc loi goc trong exception khac -> duyet ca __cause__/__context__."""
    seen = 0
    cur: BaseException | None = exc
    while cur is not None and seen < 5:
        name = type(cur).__name__
        text = str(cur).lower()
        if "ratelimit" in name.lower() or "resourceexhausted" in name.lower():
            return True
        if "resource_exhausted" in text or "429" in text or "rate limit" in text:
            return True
        cur = cur.__cause__ or cur.__context__
        seen += 1
    return False


def is_stuck(paper: dict, now: datetime | None = None) -> bool:
    """True neu paper dang 'processing' qua STUCK_JOB_AFTER ke tu created_at."""
    if paper.get("status") != "processing":
        return False
    created_at = paper.get("created_at")
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - created_at > STUCK_JOB_AFTER


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1: HEALTH CHECK
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Kiem tra tinh trang server",
    tags=["System"],
)
def health_check() -> HealthResponse:
    """
    Tra ve trang thai server.
    Dung de Streamlit hoac load-balancer xac nhan server dang hoat dong.
    """
    return HealthResponse(
        status="ok",
        version="1.0.0",
        message="ArXiv Agentic RAG API dang hoat dong binh thuong.",
    )


@router.get(
    "/health/db",
    response_model=HealthDbResponse,
    responses={503: {"model": HealthDbResponse, "description": "Khong ket noi duoc Postgres."}},
    summary="Kiem tra ket noi Postgres (SELECT 1)",
    tags=["System"],
)
async def health_db():
    """
    Chay `SELECT 1` qua pool Postgres. Vercel cron goi route nay moi ngay de
    Supabase free khong bi auto-pause sau ~7 ngay khong co query nao.
    """
    from app.storage import repository

    try:
        await asyncio.wait_for(repository.ping(), timeout=10)
    except Exception as e:
        # Khong tra chi tiet loi ra ngoai (co the lo host/user DB) - chi log server.
        print(f"[ERROR] /health/db that bai: {type(e).__name__}: {e}", flush=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "db": "unreachable"},
        )
    return HealthDbResponse(status="ok", db="ok")


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2: DANH SACH BAI BAO
# ──────────────────────────────────────────────────────────────────────────────

@protected.get(
    "/papers",
    response_model=PapersResponse,
    summary="Lay danh sach bai bao da upload",
    tags=["Papers"],
)
async def list_papers() -> PapersResponse:
    """
    Tra ve danh sach tat ca bai bao da duoc upload va index thanh cong.
    Streamlit dung endpoint nay de hien thi dropdown chon bai bao.
    """
    from app.storage import repository

    rows = await repository.list_papers()
    papers = [
        PaperInfo(
            paper_id=row["paper_id"],
            title=row["title"],
            num_chunks=row["num_chunks"],
            has_pdf=row.get("has_pdf", False),
        )
        for row in rows
    ]
    return PapersResponse(papers=papers, total=len(papers))


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3: UPLOAD PDF
# ──────────────────────────────────────────────────────────────────────────────

async def _store_pdf(pdf_path: Path, paper_id: str) -> None:
    """
    Luu PDF goc len Supabase Storage SAU khi index xong (web UI can de hien PDF).
    KHONG BAO GIO raise: Storage loi thi paper van 'ready', chi khong co has_pdf -
    khung PDF tren UI se bao "khong co ban PDF goc" thay vi hong ca bai.
    """
    from app.storage import pdf_store, repository

    if not pdf_store.is_enabled():
        return
    try:
        content = await asyncio.to_thread(pdf_path.read_bytes)
        await pdf_store.upload_pdf(paper_id, content)
        await repository.set_has_pdf(paper_id, True)
    except Exception as e:
        print(f"[WARN] Khong luu duoc PDF '{paper_id}' len Storage: {e}", flush=True)


async def _process_and_index_paper(pdf_path: Path, paper_id: str) -> None:
    """
    Chay NEN sau khi /upload da tra response 202 - khong con request nao dang
    cho de nhan HTTPException nua, nen loi o day duoc bat lai va ghi vao
    papers.status='failed' thay vi raise (raise se chi lam crash task nen
    trong im lang, client se cho status='processing' mai mai).

    Parse + embed la ham SYNC nang -> asyncio.to_thread (neu goi thang trong
    `async def`, embed_documents() time.sleep(61) se dong bang ca event loop,
    /health va moi request khac treo theo). _index_lock: xem comment o dau file.
    """
    from app.storage import repository

    try:
        async with _index_lock:
            from app.ingestion.chunker import process_paper_ingestion

            # Khong dung cache JSON cua Phase 1 (load_chunks_from_file) - cache do
            # chi luu ChildChunk, khong luu ParentSection, se mat du lieu sections
            # can cho insert_sections() ben duoi. Parse lai moi lan upload.
            sections, chunks = await asyncio.to_thread(
                process_paper_ingestion, pdf_path, paper_id=paper_id
            )

            from app.indexing.embeddings import get_embedding_provider

            provider = get_embedding_provider()
            embeddings = await asyncio.to_thread(
                provider.embed_documents, [c.text for c in chunks]
            )

        section_pk_map = await repository.insert_sections(paper_id, sections)
        await repository.insert_chunks(paper_id, chunks, embeddings, section_pk_map)
        await repository.set_paper_status(paper_id, status="ready", num_chunks=len(chunks))
        await _store_pdf(pdf_path, paper_id)
    except Exception as e:
        print(f"[ERROR] Xu ly nen paper_id='{paper_id}' that bai: {e}", flush=True)
        try:
            await repository.set_paper_status(paper_id, status="failed")
        except Exception as e2:
            # DB cung hong -> khong lam gi them duoc; GET status se tu danh dau
            # 'failed' sau STUCK_JOB_AFTER.
            print(f"[ERROR] Khong ghi duoc status='failed' cho '{paper_id}': {e2}", flush=True)


def _should_reuse_by_hash(existing: dict | None) -> bool:
    """
    Quyet dinh co tai su dung paper da index truoc do (cung file_hash) hay
    khong, thay vi parse+embed lai tu dau (ton quota Gemini free-tier).
    Chi tai su dung khi paper cu da 'ready' - neu dang 'processing' (hiem,
    race condition) hoac 'failed' (lan truoc loi giua chung), coi nhu chua
    co gi dang tin cay de tai su dung, xu ly nhu 1 upload moi binh thuong.
    """
    return existing is not None and existing["status"] == "ready"


def _should_clear_stale_hash(existing: dict | None) -> bool:
    """
    True neu tim thay 1 paper cu cung file_hash nhung KHONG the tai su dung
    (_should_reuse_by_hash tra False phia tren) - tuc paper do dang
    'processing' hoac da 'failed'. Paper do van dang "giu" claim tren cot
    `papers.file_hash UNIQUE` (db/schema.sql dat UNIQUE nay cho TOAN BANG,
    khong scope rieng theo status='ready'), nen phai go claim cu truoc khi
    ghi row moi cung file_hash o nhanh fresh-upload ben duoi - neu khong
    upsert_paper() se nem asyncpg.exceptions.UniqueViolationError (bug tim
    thay khi review Task 3: 'fresh upload' fallback crash 500 thay vi thanh
    cong).
    """
    return existing is not None and not _should_reuse_by_hash(existing)


async def _register_and_queue(
    background_tasks: BackgroundTasks,
    response: Response,
    *,
    content: bytes,
    paper_id: str,
    title: str,
    filename: str,
) -> UploadResponse:
    """
    Phan dung chung cua /upload va /papers/arxiv (content da validate xong):
    dedup theo sha256 -> go claim file_hash cu neu can -> luu file -> upsert paper
    (status='processing') -> xep job index chay nen. Tra 200 (paper cu 'ready') hoac
    202 (job moi) qua `response.status_code` + UploadResponse.
    """
    from app.storage import repository

    file_hash = hashlib.sha256(content).hexdigest()

    existing = await repository.get_paper_by_hash(file_hash)
    if _should_reuse_by_hash(existing):
        response.status_code = status.HTTP_200_OK
        return UploadResponse(
            paper_id=existing["paper_id"],
            title=existing["title"],
            status="ready",
            num_chunks=existing["num_chunks"],
            message=f"File nay da duoc upload va index truoc do "
                    f"(paper_id='{existing['paper_id']}'). Khong xu ly lai de "
                    f"tiet kiem quota Gemini free-tier.",
        )

    if _should_clear_stale_hash(existing):
        # Paper cu cung file_hash dang 'processing'/'failed' - go claim cu
        # tren cot file_hash truoc khi ghi row moi cung file_hash ben duoi,
        # neu khong se dam vao UniqueViolationError (schema.sql UNIQUE toan
        # bang, khong rieng status='ready').
        await repository.clear_stale_file_hash(existing["paper_id"])

    # ── Luu file PDF vao thu muc data/, dat ten theo paper_id (KHONG phai
    # ten file goc) - 2 paper_id khac nhau upload file trung ten se KHONG
    # con ghi de len nhau tren disk nhu truoc (bug that: da lam mat 1 file
    # PDF mau that trong luc test tinh nang DELETE) ──
    pdf_path = settings.data_dir / f"{paper_id}.pdf"
    try:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi khi luu file: {e}",
        )

    try:
        await repository.upsert_paper(
            paper_id=paper_id,
            title=title,
            filename=filename,
            file_hash=file_hash,
            status="processing",
        )
    except asyncpg.exceptions.UniqueViolationError:
        # Phong ngua da co _should_clear_stale_hash() phia tren, truong hop
        # nay chi con xay ra do race condition that (2 request dung file_hash
        # gan nhau). Xoa file PDF vua ghi de khong mo côi tren dia (cung
        # nguyen tac voi khoi except ben tren cho loi ghi file) - dung de lai
        # file khong co paper row nao tro toi, dung y het bug #12.
        pdf_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Loi: file_hash bi trung luc ghi paper moi (rat co the do "
                    "2 request gan nhau cung upload 1 file). Vui long thu lai.",
        )
    background_tasks.add_task(_process_and_index_paper, pdf_path, paper_id)

    return UploadResponse(
        paper_id=paper_id,
        title=title,
        status="processing",
        num_chunks=0,
        message="Da nhan file, dang parse + embed + index nen. "
                f"Goi GET /papers/{paper_id}/status de kiem tra tien do.",
    )


@protected.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {
            "model": UploadResponse,
            "description": "File (theo sha256) da duoc index truoc do - tra ve "
                           "paper cu (paper_id goc, status='ready'), khong xu ly lai.",
        },
        202: {
            "description": "Da nhan file moi, status='processing' - parse/embed/"
                           "index chay nen, poll GET /papers/{paper_id}/status.",
        },
        400: {"description": "Khong phai PDF (.pdf + header %PDF) hoac paper_id sai dinh dang."},
        413: {"description": "File vuot max_upload_mb - dung POST /papers/arxiv."},
    },
    summary="Upload file PDF bai bao, index chay nen",
    tags=["Papers"],
)
async def upload_paper(
    background_tasks: BackgroundTasks,
    response: Response,
    file: UploadFile = File(..., description="File PDF bai bao can upload."),
    paper_id: str | None = Form(
        default=None,
        description="ID tuy chinh cho bai bao (a-z, 0-9, '-', '_', toi da 64 ky tu). "
                    "Neu bo trong, tu dong tao tu ten file + 6 ky tu ngau nhien.",
    ),
) -> UploadResponse:
    """
    Upload 1 file PDF (toi da `max_upload_mb`, mac dinh 4 MB). Neu noi dung file
    (theo sha256) da duoc index thanh cong truoc do (bat ky paper_id nao), tra ve
    luon thong tin paper cu, KHONG parse+embed lai (tiet kiem quota Gemini
    free-tier) - xem _should_reuse_by_hash.
    Nguoc lai: luu file + tao paper (status="processing") roi tra ve 202 NGAY -
    parse/embed/index chay nen (co the mat hang chuc giay do Gemini free-tier
    rate-limit cooldown, xem app/indexing/embeddings.py). Goi
    GET /papers/{paper_id}/status de biet khi nao xong.
    """
    # ── Validate file ──
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chi chap nhan file PDF (.pdf).",
        )

    if paper_id:
        validate_paper_id(paper_id)

    # Doc toi da limit+1 byte: du de biet file co vuot gioi han hay khong ma khong
    # nap ca file khong lo vao RAM.
    max_bytes = int(settings.max_upload_mb * 1024 * 1024)
    content = await file.read(max_bytes + 1)
    enforce_upload_limit(content)
    ensure_pdf(content)

    return await _register_and_queue(
        background_tasks,
        response,
        content=content,
        paper_id=paper_id or make_paper_id(file.filename),
        title=Path(file.filename).stem,
        filename=file.filename,
    )


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3a: IMPORT THEO ARXIV ID
# ──────────────────────────────────────────────────────────────────────────────

async def _download_arxiv_pdf(arxiv_id: str) -> bytes:
    """Tai PDF tu arxiv.org (stream, cat o ARXIV_MAX_PDF_BYTES). Loi mang -> 502/504."""
    url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)
    headers = {"User-Agent": ARXIV_USER_AGENT}
    try:
        async with asyncio.timeout(60):
            async with httpx.AsyncClient(
                timeout=30, follow_redirects=True, headers=headers
            ) as client, client.stream("GET", url) as r:
                if r.status_code == 404:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Khong tim thay bai bao arXiv '{arxiv_id}'.",
                    )
                if r.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"arxiv.org tra ve HTTP {r.status_code}.",
                    )
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > ARXIV_MAX_PDF_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"PDF tren arXiv vuot {ARXIV_MAX_PDF_BYTES // (1024 * 1024)} MB.",
                        )
                return bytes(buf)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Tai PDF tu arxiv.org qua thoi gian cho.",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Khong tai duoc PDF tu arxiv.org: {type(e).__name__}.",
        )


def parse_arxiv_title(xml_text: str) -> str | None:
    """Rut <title> cua entry dau tien trong Atom feed cua arXiv API; None neu khong co."""
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = ET.fromstring(xml_text).find("a:entry", ns)
    if entry is None:
        return None
    title = entry.findtext("a:title", default="", namespaces=ns)
    title = " ".join(title.split())  # gop xuong dong/khoang trang thua trong title
    return title or None


async def _fetch_arxiv_title(arxiv_id: str) -> str:
    """Best-effort: lay title that tu arXiv API; bat ky loi nao -> dung arxiv_id lam title."""
    try:
        async with httpx.AsyncClient(
            timeout=10, follow_redirects=True, headers={"User-Agent": ARXIV_USER_AGENT}
        ) as client:
            r = await client.get(ARXIV_API_URL.format(arxiv_id=arxiv_id))
            r.raise_for_status()
        return parse_arxiv_title(r.text) or arxiv_id
    except Exception as e:
        print(f"[WARN] Khong lay duoc title arXiv '{arxiv_id}': {type(e).__name__}", flush=True)
        return arxiv_id


@protected.post(
    "/papers/arxiv",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"model": UploadResponse, "description": "Paper da index truoc do - khong xu ly lai."},
        202: {"description": "Da tai PDF, status='processing' - poll GET /papers/{paper_id}/status."},
        400: {"description": "arxiv_id sai dinh dang."},
        404: {"description": "arXiv khong co bai bao nay."},
        502: {"description": "Khong tai duoc PDF tu arxiv.org."},
    },
    summary="Import bai bao theo arXiv ID, index chay nen",
    tags=["Papers"],
)
async def import_arxiv_paper(
    body: ArxivImportRequest,
    background_tasks: BackgroundTasks,
    response: Response,
) -> UploadResponse:
    """
    Server tu tai PDF tu `https://arxiv.org/pdf/<id>` (toi da 30 MB) roi di tiep
    luong nhu /upload (dedup sha256 -> index nen). Cach nay vuot gioi han body
    4.5 MB cua Vercel. paper_id = 'arxiv-<id>' (co dinh theo id nen import lai
    cung bai khong tao ban trung).
    """
    from app.storage import repository

    arxiv_id = validate_arxiv_id(body.arxiv_id)
    paper_id = f"arxiv-{arxiv_id}"

    # Da co paper nay roi thi khong can cham arxiv.org: 'ready' -> 200; dang
    # 'processing' (chua ket) -> tra lai 202 ma khong xep them job thu hai.
    existing = await repository.get_paper(paper_id)
    if existing is not None and existing["status"] == "ready":
        response.status_code = status.HTTP_200_OK
        return UploadResponse(
            paper_id=paper_id,
            title=existing["title"],
            status="ready",
            num_chunks=existing["num_chunks"],
            message=f"Bai bao arXiv {arxiv_id} da duoc index truoc do.",
        )
    if existing is not None and existing["status"] == "processing" and not is_stuck(existing):
        return UploadResponse(
            paper_id=paper_id,
            title=existing["title"],
            status="processing",
            num_chunks=0,
            message=f"Bai bao arXiv {arxiv_id} dang duoc xu ly. "
                    f"Goi GET /papers/{paper_id}/status de kiem tra tien do.",
        )

    content = await _download_arxiv_pdf(arxiv_id)
    ensure_pdf(content, status_code=status.HTTP_502_BAD_GATEWAY)
    title = await _fetch_arxiv_title(arxiv_id)

    return await _register_and_queue(
        background_tasks,
        response,
        content=content,
        paper_id=paper_id,
        title=title,
        filename=f"{arxiv_id}.pdf",
    )


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3b: TRANG THAI XU LY 1 PAPER (poll sau /upload)
# ──────────────────────────────────────────────────────────────────────────────

@protected.get(
    "/papers/{paper_id}/status",
    response_model=PaperStatusResponse,
    summary="Kiem tra tien do xu ly 1 paper sau khi upload",
    tags=["Papers"],
)
async def get_paper_status(paper_id: str) -> PaperStatusResponse:
    """Client poll endpoint nay sau /upload cho den khi status='ready' (hoac
    'failed'). Khac /papers (chi liet ke paper 'ready') - endpoint nay tra ve
    ca paper dang 'processing'/'failed' vi client can biet chinh xac paper
    do dang o trang thai nao.

    Job 'processing' qua 15 phut (STUCK_JOB_AFTER) coi nhu da chet - function bi
    kill giua chung (vd Vercel het maxDuration) se khong bao gio cap nhat row nua
    - nen duoc danh dau 'failed' tai day de client khong cho mai mai."""
    from app.storage import repository

    validate_lookup_id(paper_id)
    paper = await repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay paper_id='{paper_id}'.",
        )
    if is_stuck(paper):
        await repository.set_paper_status(paper_id, status="failed")
        paper = {**paper, "status": "failed"}
    return PaperStatusResponse(
        paper_id=paper["paper_id"],
        title=paper["title"],
        status=paper["status"],
        num_chunks=paper["num_chunks"],
        has_pdf=paper.get("has_pdf", False),
    )


@protected.get(
    "/papers/{paper_id}/pdf-url",
    response_model=PdfUrlResponse,
    summary="Signed URL de xem PDF goc",
    tags=["Papers"],
    responses={
        404: {"description": "Khong co paper, paper khong co PDF, hoac Storage chua cau hinh."},
        502: {"description": "Supabase Storage loi."},
    },
)
async def get_pdf_url(paper_id: str) -> PdfUrlResponse:
    """
    Tra signed URL (het han sau 1 gio) de trinh duyet tai PDF thang tu Supabase
    Storage - PDF khong di qua API vi Vercel cat response > 4.5 MB.
    """
    from app.storage import pdf_store, repository

    validate_lookup_id(paper_id)
    paper = await repository.get_paper(paper_id)
    if paper is None or not paper.get("has_pdf") or not pdf_store.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bai nay khong co ban PDF goc.",
        )
    try:
        url = await pdf_store.signed_url(paper_id)
    except Exception as e:
        print(f"[ERROR] Khong tao duoc signed URL cho '{paper_id}': {e}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Khong lay duoc link PDF tu Storage.",
        )
    return PdfUrlResponse(url=url, expires_in=pdf_store.SIGNED_URL_TTL)


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3c: XOA 1 PAPER
# ──────────────────────────────────────────────────────────────────────────────

@protected.delete(
    "/papers/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xoa 1 paper va toan bo du lieu lien quan",
    tags=["Papers"],
)
async def delete_paper(paper_id: str) -> None:
    """
    Xoa 1 paper khoi Postgres - `sections`/`chunks`/`paper_cards` tu dong bi
    xoa theo qua `ON DELETE CASCADE` (db/schema.sql), khong can xoa tay tung
    bang. File PDF goc tren disk cung duoc xoa neu con ton tai.

    Neu goi trong luc paper dang o trang thai 'processing' (background task
    cua /upload chua xong): task nen se tiep tuc chay nhung insert_sections/
    insert_chunks se that bai vi FK paper_id khong con - _process_and_index_paper()
    da bat loi nay va goi set_paper_status() (khong lam gi vi row da mat), khong
    crash task nen.
    """
    from app.storage import repository

    validate_lookup_id(paper_id)  # paper_id duoc noi vao duong dan file de unlink
    paper = await repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay paper_id='{paper_id}'.",
        )

    await repository.delete_paper(paper_id)

    from app.storage import pdf_store

    if pdf_store.is_enabled():
        try:
            await pdf_store.delete_pdf(paper_id)
        except Exception as e:
            # Row da xoa -> object mo coi chi ton dung luong, khong anh huong nguoi dung.
            print(f"[WARN] Khong xoa duoc PDF '{paper_id}' tren Storage: {e}", flush=True)

    pdf_path = settings.data_dir / f"{paper_id}.pdf"
    if pdf_path.exists():
        pdf_path.unlink()


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 4: ASK — Hoi Agent
# ──────────────────────────────────────────────────────────────────────────────

@protected.post(
    "/ask",
    response_model=AskResponse,
    summary="Hoi Agent ve noi dung bai bao",
    tags=["Chat"],
)
async def ask_agent(body: AskRequest) -> AskResponse:
    """
    Gui cau hoi toi LangGraph RAG Agent va nhan cau tra loi.

    - Agent tu dong nho lich su hoi thoai qua `thread_id`.
    - Neu `thread_id` la None, server se tao 1 thread_id moi.
    - Tra ve cau tra loi, nguon trich dan, so lan rewrite va grade.
    """
    from app.agent.rag_graph import ask
    from app.storage import repository

    # Kiem tra paper ton tai
    paper = await repository.get_paper(body.paper_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay paper_id='{body.paper_id}'. "
                   f"Vui long upload bai bao truoc.",
        )

    # Tao thread_id moi neu client khong gui
    thread_id = body.thread_id or f"auto_{uuid.uuid4().hex[:8]}"

    # Goi Agent
    try:
        result = await ask(
            question=body.question,
            paper_id=body.paper_id,
            thread_id=thread_id,
        )
    except Exception as e:
        print(f"[ERROR] /ask paper_id='{body.paper_id}': {type(e).__name__}: {e}", flush=True)
        if is_quota_error(e):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Het quota dich vu AI, thu lai sau.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Loi Agent.",
        )

    # Lay cau tra loi tu AgentState
    messages = result.get("messages", [])
    answer = messages[-1].content if messages else "Khong co cau tra loi."

    # Trich xuat source chunks de hien thi tren UI
    raw_chunks = result.get("retrieved_chunks", [])
    sources = [
        SourceChunk(
            chunk_id=chunk.get("chunk_id", "unknown"),
            section=chunk.get("parent_section_name", "Unknown section"),
            content_preview=chunk.get("text", "")[:150],
            page_num=chunk.get("page_num"),
            text=chunk.get("text", ""),
        )
        for chunk in raw_chunks
    ]

    return AskResponse(
        answer=answer,
        thread_id=thread_id,
        grade=result.get("grade", "yes"),
        rewrite_count=result.get("rewrite_count", 0),
        sources=sources,
    )


# Dang ky cac route can API key vao router goc (phai dat SAU khi da khai bao het route).
router.include_router(protected)
