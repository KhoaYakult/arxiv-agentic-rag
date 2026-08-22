"""
app/api/routes.py
==================
Dinh nghia cac endpoint REST API cua ung dung.

Cac endpoint:
  GET  /health          — Kiem tra server dang song
  GET  /papers          — Lay danh sach bai bao da duoc index
  POST /upload          — Upload PDF -> parse -> chunk -> index vao ChromaDB
  POST /ask             — Hoi Agent va nhan cau tra loi

Luong xu ly /upload:
  PDF file -> chunker.process_paper_ingestion()
           -> VectorStoreManager.add_chunks()
           -> BM25StoreManager.build_index()

Luong xu ly /ask:
  AskRequest -> rag_graph.ask() -> AskResponse
"""

from __future__ import annotations

import json
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
# HELPER: doc file trang thai bai bao da upload (luu o JSON don gian)
# ──────────────────────────────────────────────────────────────────────────────

_PAPERS_REGISTRY = settings.data_dir / "papers_registry.json"


def _load_registry() -> dict[str, dict]:
    """Doc registry tu file JSON. Tra ve {} neu file chua ton tai."""
    if _PAPERS_REGISTRY.exists():
        with open(_PAPERS_REGISTRY, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_registry(registry: dict[str, dict]) -> None:
    """Ghi registry xuong file JSON."""
    with open(_PAPERS_REGISTRY, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


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
def list_papers() -> PapersResponse:
    """
    Tra ve danh sach tat ca bai bao da duoc upload va index thanh cong.
    Streamlit dung endpoint nay de hien thi dropdown chon bai bao.
    """
    registry = _load_registry()
    papers = [
        PaperInfo(
            paper_id=pid,
            title=info.get("title", pid),
            num_chunks=info.get("num_chunks", 0),
        )
        for pid, info in registry.items()
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
    4. Index chunks vao ChromaDB (Dense Vector)
    5. Build/cap nhat BM25 Index (Sparse Vector)
    6. Luu thong tin vao registry
    """

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
    try:
        from app.ingestion.chunker import load_chunks_from_file, process_paper_ingestion
        from app.indexing.bm25_store import BM25StoreManager
        from app.indexing.vector_store import VectorStoreManager

        # Thu load tu cache truoc (neu da xu ly roi)
        chunks = load_chunks_from_file(paper_id)
        if chunks is None:
            _, chunks = process_paper_ingestion(pdf_path, paper_id=paper_id)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Loi khi xu ly PDF: {e}",
        )

    # ── Index vao ChromaDB ──
    # Dung method add_child_chunks() co san trong VectorStoreManager
    # (da duoc test ky, xu ly embed API batching va progress log dung chuan)
    try:
        vm = VectorStoreManager()
        vm.add_child_chunks(chunks)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi khi index vao ChromaDB: {e}",
        )

    # ── Build / cap nhat BM25 ──
    try:
        bm25_mgr = BM25StoreManager()
        bm25_mgr.build_index(chunks)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi khi build BM25: {e}",
        )

    # ── Luu vao registry ──
    registry = _load_registry()
    registry[paper_id] = {
        "title": Path(file.filename).stem,
        "filename": file.filename,
        "num_chunks": len(chunks),
    }
    _save_registry(registry)

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
def ask_agent(body: AskRequest) -> AskResponse:
    """
    Gui cau hoi toi LangGraph RAG Agent va nhan cau tra loi.

    - Agent tu dong nho lich su hoi thoai qua `thread_id`.
    - Neu `thread_id` la None, server se tao 1 thread_id moi.
    - Tra ve cau tra loi, nguon trich dan, so lan rewrite va grade.
    """
    from app.agent.rag_graph import ask

    # Kiem tra paper ton tai
    registry = _load_registry()
    if body.paper_id not in registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay paper_id='{body.paper_id}'. "
                   f"Vui long upload bai bao truoc.",
        )

    # Tao thread_id moi neu client khong gui
    thread_id = body.thread_id or f"auto_{uuid.uuid4().hex[:8]}"

    # Goi Agent
    try:
        result = ask(
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
    raw_docs = result.get("documents", [])
    sources = [
        SourceChunk(
            chunk_id=doc.metadata.get("chunk_id", "unknown"),
            section=doc.metadata.get("section", "Unknown section"),
            content_preview=doc.page_content[:150],
        )
        for doc in raw_docs
    ]

    return AskResponse(
        answer=answer,
        thread_id=thread_id,
        grade=result.get("grade", "yes"),
        rewrite_count=result.get("rewrite_count", 0),
        sources=sources,
    )
