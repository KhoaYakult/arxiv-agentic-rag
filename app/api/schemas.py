"""
app/api/schemas.py
==================
Dinh nghia cau truc du lieu (Schema) cho toan bo API.

Pydantic tu dong:
  - Validate kieu du lieu (int, str, list...) khi nhan request.
  - Serialize Python object -> JSON khi tra response.
  - Sinh tai lieu Swagger UI tu cac model nay.

Quy tac dat ten:
  - *Request : Du lieu CLIENT gui len server.
  - *Response: Du lieu SERVER tra ve cho client.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# UPLOAD PAPER
# ──────────────────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    """Ket qua sau khi upload va xu ly xong 1 file PDF."""

    paper_id: str = Field(
        description="ID duy nhat cua bai bao (slug tu ten file PDF)."
    )
    title: str = Field(
        description="Ten bai bao (lay tu ten file PDF)."
    )
    num_chunks: int = Field(
        description="Tong so child-chunks da duoc index vao ChromaDB."
    )
    message: str = Field(
        description="Thong bao ket qua xu ly."
    )


# ──────────────────────────────────────────────────────────────────────────────
# ASK — Goi Agent de tra loi cau hoi
# ──────────────────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    """Du lieu client gui len khi hoi mot cau hoi."""

    question: str = Field(
        min_length=3,
        max_length=1000,
        description="Cau hoi cua nguoi dung (tieng Anh hoac tieng Viet).",
        examples=["What is CortexODE?"],
    )
    paper_id: str = Field(
        description="paper_id cua bai bao muon hoi (nhan duoc sau khi upload).",
        examples=["cortex_ode_2023"],
    )
    thread_id: str | None = Field(
        default=None,
        description=(
            "ID phien hoi thoai de Agent nho lich su chat. "
            "Neu None, server se tu tao moi."
        ),
        examples=["user_abc_session_1"],
    )


class SourceChunk(BaseModel):
    """Thong tin 1 doan van ban nguon duoc Agent su dung de tra loi."""

    chunk_id: str = Field(description="ID duy nhat cua chunk.")
    section: str = Field(description="Ten section trong bai bao.")
    content_preview: str = Field(description="100 ky tu dau cua noi dung chunk.")


class AskResponse(BaseModel):
    """Ket qua tra loi tu Agent."""

    answer: str = Field(description="Cau tra loi da duoc tong hop boi LLM.")
    thread_id: str = Field(description="Thread ID cua phien hoi thoai hien tai.")
    grade: Literal["yes", "no"] = Field(
        description="LLM tu danh gia tai lieu co du de tra loi khong (yes/no)."
    )
    rewrite_count: int = Field(
        description="So lan Agent da phai viet lai cau hoi de tim kiem tot hon."
    )
    sources: list[SourceChunk] = Field(
        default_factory=list,
        description="Danh sach cac doan van ban nguon duoc Agent su dung.",
    )


# ──────────────────────────────────────────────────────────────────────────────
# PAPERS — Danh sach bai bao da duoc index
# ──────────────────────────────────────────────────────────────────────────────

class PaperInfo(BaseModel):
    """Thong tin tom tat cua 1 bai bao da duoc index."""

    paper_id: str = Field(description="ID duy nhat cua bai bao.")
    title: str = Field(description="Ten bai bao (lay tu ten file PDF).")
    num_chunks: int = Field(description="So luong chunks trong ChromaDB.")


class PapersResponse(BaseModel):
    """Danh sach tat ca bai bao da duoc xu ly va index."""

    papers: list[PaperInfo] = Field(
        default_factory=list,
        description="Danh sach cac bai bao da upload.",
    )
    total: int = Field(description="Tong so bai bao.")


# ──────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ──────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Ket qua kiem tra tinh trang server."""

    status: Literal["ok", "error"] = Field(description="Trang thai server.")
    version: str = Field(default="1.0.0", description="Phien ban API.")
    message: str = Field(description="Thong bao.")
