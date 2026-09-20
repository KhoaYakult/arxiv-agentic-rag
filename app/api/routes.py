"""
app/api/routes.py
==================
Dinh nghia cac endpoint REST API cua ung dung.

Cac endpoint:
  GET  /health          — Kiem tra server dang song
  GET  /papers          — Lay danh sach bai bao da duoc index
  POST /upload          — Upload PDF -> parse -> chunk -> index vao Postgres
  POST /ask             — Hoi Agent va nhan cau tra loi

Luong xu ly /upload (Phase 2 - Postgres/Supabase):
  PDF file -> chunker.process_paper_ingestion()
           -> embeddings.get_embedding_provider().embed_documents()
           -> repository.upsert_paper() + insert_sections() + insert_chunks()

Luong xu ly /ask:
  AskRequest -> rag_graph.ask() -> AskResponse

Phase 1 (ChromaDB + BM25 pickle) da bi thay the hoan toan o day - xem
project-memory/STATE.md truoc khi xoa app/indexing/vector_store.py va
bm25_store.py (chi xoa sau khi cutover nay da test lai end-to-end that
nhu da lam voi Phase 1).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.schemas import (
    AskRequest,
    AskResponse,
    HealthResponse,
    PaperInfo,
    PapersResponse,
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

@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload file PDF bai bao va tu dong index",
    tags=["Papers"],
)
async def upload_paper(
    file: UploadFile = File(..., description="File PDF bai bao can upload."),
    paper_id: str | None = Form(
        default=None,
        description="ID tuy chinh cho bai bao. Neu bo trong, tu dong tao tu ten file.",
    ),
) -> UploadResponse:
    """
    Upload 1 file PDF, sau do tu dong:
    1. Luu file vao thu muc data/
    2. Parse PDF -> Markdown (dung pymupdf4llm)
    3. Chunk Markdown -> Parent Sections + Child Chunks
    4. Embed chunks (Gemini) + ghi papers/sections/chunks vao Postgres
    """
    from app.storage import repository

    # ── Validate file ──
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chi chap nhan file PDF (.pdf).",
        )

    # ── Tao paper_id tu ten file neu khong truyen vao ──
    if not paper_id:
        stem = Path(file.filename).stem  # bo duoi .pdf
        # Chuyen thanh slug: chi giu chu/so/gach duoi, viet thuong
        paper_id = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in stem.lower()
        ).strip("_")

    # ── Luu file PDF vao thu muc data/ ──
    pdf_path = settings.data_dir / file.filename
    try:
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi khi luu file: {e}",
        )

    # ── Parse PDF + Chunk ──
    # Luu y: khong dung cache JSON cua Phase 1 (load_chunks_from_file) nua -
    # cache do chi luu ChildChunk, khong luu ParentSection, nen se mat du lieu
    # sections can cho insert_sections() ben duoi. Parse lai moi lan upload.
    try:
        from app.ingestion.chunker import process_paper_ingestion

        sections, chunks = process_paper_ingestion(pdf_path, paper_id=paper_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Loi khi xu ly PDF: {e}",
        )

    # ── Embed chunks (Gemini) ──
    try:
        from app.indexing.embeddings import get_embedding_provider

        provider = get_embedding_provider()
        embeddings = provider.embed_documents([c.text for c in chunks])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi khi tao embedding: {e}",
        )

    # ── Ghi vao Postgres (papers + sections + chunks) ──
    try:
        await repository.upsert_paper(
            paper_id=paper_id,
            title=Path(file.filename).stem,
            filename=file.filename,
            status="processing",
        )
        section_pk_map = await repository.insert_sections(paper_id, sections)
        await repository.insert_chunks(paper_id, chunks, embeddings, section_pk_map)
        await repository.set_paper_status(paper_id, status="ready", num_chunks=len(chunks))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi khi ghi vao Postgres: {e}",
        )

    return UploadResponse(
        paper_id=paper_id,
        title=Path(file.filename).stem,
        num_chunks=len(chunks),
        message=f"Upload va index thanh cong! {len(chunks)} chunks da san sang.",
    )


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
