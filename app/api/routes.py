"""
app/api/routes.py
==================
Dinh nghia cac endpoint REST API cua ung dung.

Cac endpoint:
  GET    /health                  — Kiem tra server dang song
  GET    /papers                  — Lay danh sach bai bao status='ready'
  POST   /upload                  — Upload PDF, index chay nen (BackgroundTasks), tra 202
                                     (hoac 200 neu file da index truoc do - dedup sha256)
  GET    /papers/{id}/status      — Poll tien do xu ly sau /upload
  DELETE /papers/{id}             — Xoa paper (cascade sections/chunks/paper_cards)
  POST   /ask                     — Hoi Agent va nhan cau tra loi

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

Luong xu ly /ask:
  AskRequest -> rag_graph.ask() -> AskResponse

Phase 1 (ChromaDB + BM25 pickle, app/indexing/vector_store.py + bm25_store.py)
da bi thay the hoan toan o day va sau do xoa het khoi repo (xem
project-memory/FIXED_BUGS.md va git history neu can xem lai code cu).
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import asyncpg
from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)

from app.api.schemas import (
    AskRequest,
    AskResponse,
    HealthResponse,
    PaperInfo,
    PapersResponse,
    PaperStatusResponse,
    SourceChunk,
    UploadResponse,
)
from app.config import settings

router = APIRouter()


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


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2: DANH SACH BAI BAO
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
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
        )
        for row in rows
    ]
    return PapersResponse(papers=papers, total=len(papers))


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3: UPLOAD PDF
# ──────────────────────────────────────────────────────────────────────────────

async def _process_and_index_paper(pdf_path: Path, paper_id: str) -> None:
    """
    Chay NEN sau khi /upload da tra response 202 - khong con request nao dang
    cho de nhan HTTPException nua, nen loi o day duoc bat lai va ghi vao
    papers.status='failed' thay vi raise (raise se chi lam crash task nen
    trong im lang, client se cho status='processing' mai mai).
    """
    from app.storage import repository

    try:
        from app.ingestion.chunker import process_paper_ingestion

        # Khong dung cache JSON cua Phase 1 (load_chunks_from_file) - cache do
        # chi luu ChildChunk, khong luu ParentSection, se mat du lieu sections
        # can cho insert_sections() ben duoi. Parse lai moi lan upload.
        sections, chunks = process_paper_ingestion(pdf_path, paper_id=paper_id)

        from app.indexing.embeddings import get_embedding_provider

        provider = get_embedding_provider()
        embeddings = provider.embed_documents([c.text for c in chunks])

        section_pk_map = await repository.insert_sections(paper_id, sections)
        await repository.insert_chunks(paper_id, chunks, embeddings, section_pk_map)
        await repository.set_paper_status(paper_id, status="ready", num_chunks=len(chunks))
    except Exception as e:
        print(f"[ERROR] Xu ly nen paper_id='{paper_id}' that bai: {e}", flush=True)
        await repository.set_paper_status(paper_id, status="failed")


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
    cong, xem project-memory/FIXED_BUGS.md).
    """
    return existing is not None and not _should_reuse_by_hash(existing)


@router.post(
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
        description="ID tuy chinh cho bai bao. Neu bo trong, tu dong tao tu ten file.",
    ),
) -> UploadResponse:
    """
    Upload 1 file PDF. Neu noi dung file (theo sha256) da duoc index thanh
    cong truoc do (bat ky paper_id nao), tra ve luon thong tin paper cu, KHONG
    parse+embed lai (tiet kiem quota Gemini free-tier) - xem _should_reuse_by_hash.
    Nguoc lai: luu file + tao paper (status="processing") roi tra ve 202 NGAY -
    parse/embed/index chay nen (co the mat hang chuc giay do Gemini free-tier
    rate-limit cooldown, xem app/indexing/embeddings.py). Goi
    GET /papers/{paper_id}/status de biet khi nao xong.
    """
    from app.storage import repository

    # ── Validate file ──
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chi chap nhan file PDF (.pdf).",
        )

    content = await file.read()
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

    # ── Tao paper_id tu ten file neu khong truyen vao ──
    if not paper_id:
        stem = Path(file.filename).stem  # bo duoi .pdf
        # Chuyen thanh slug: chi giu chu/so/gach duoi, viet thuong
        paper_id = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in stem.lower()
        ).strip("_")

    # ── Luu file PDF vao thu muc data/, dat ten theo paper_id (KHONG phai
    # ten file goc) - 2 paper_id khac nhau upload file trung ten se KHONG
    # con ghi de len nhau tren disk nhu truoc (bug that: da lam mat 1 file
    # PDF mau that trong luc test tinh nang DELETE, xem project-memory/FIXED_BUGS.md #12) ──
    pdf_path = settings.data_dir / f"{paper_id}.pdf"
    try:
        pdf_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi khi luu file: {e}",
        )

    title = Path(file.filename).stem
    try:
        await repository.upsert_paper(
            paper_id=paper_id,
            title=title,
            filename=file.filename,
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


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3b: TRANG THAI XU LY 1 PAPER (poll sau /upload)
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/papers/{paper_id}/status",
    response_model=PaperStatusResponse,
    summary="Kiem tra tien do xu ly 1 paper sau khi upload",
    tags=["Papers"],
)
async def get_paper_status(paper_id: str) -> PaperStatusResponse:
    """Client poll endpoint nay sau /upload cho den khi status='ready' (hoac
    'failed'). Khac /papers (chi liet ke paper 'ready') - endpoint nay tra ve
    ca paper dang 'processing'/'failed' vi client can biet chinh xac paper
    do dang o trang thai nao."""
    from app.storage import repository

    paper = await repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay paper_id='{paper_id}'.",
        )
    return PaperStatusResponse(
        paper_id=paper["paper_id"],
        title=paper["title"],
        status=paper["status"],
        num_chunks=paper["num_chunks"],
    )


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3c: XOA 1 PAPER
# ──────────────────────────────────────────────────────────────────────────────

@router.delete(
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

    paper = await repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay paper_id='{paper_id}'.",
        )

    await repository.delete_paper(paper_id)

    pdf_path = settings.data_dir / f"{paper_id}.pdf"
    if pdf_path.exists():
        pdf_path.unlink()


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINT 4: ASK — Hoi Agent
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi Agent: {e}",
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
