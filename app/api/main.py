"""
app/api/main.py
================
Diem khoi dong chinh cua FastAPI server.

Chuc nang:
  - Tao FastAPI app voi metadata (title, description, version).
  - Cau hinh CORS cho phep Streamlit (chay o port khac) goi API.
  - Dang ky router chua cac endpoint.
  - Cung cap tai lieu Swagger UI tai /docs va ReDoc tai /redoc.

Cach chay server:
    uvicorn app.api.main:app --reload --port 8000

Sau khi chay, mo trinh duyet va truy cap:
    http://localhost:8000/docs   → Swagger UI (test API truc tiep)
    http://localhost:8000/redoc  → ReDoc (tai lieu dep hon)
"""

import sys
from pathlib import Path

# Them thu muc goc du an vao sys.path de cac import tuong doi hoat dong
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router


# ──────────────────────────────────────────────────────────────────────────────
# KHOI TAO FASTAPI APP
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ArXiv Agentic RAG API",
    description=(
        "API Backend cho he thong Agentic RAG tren bai bao ArXiv.\n\n"
        "## Tinh nang\n"
        "- **Upload** file PDF bai bao khoa hoc\n"
        "- **Hoi** Agent ve noi dung bai bao (co nho lich su hoi thoai)\n"
        "- **Xem** danh sach bai bao da duoc index\n\n"
        "## Cong nghe\n"
        "- LangGraph (Corrective RAG Agent)\n"
        "- ChromaDB + BM25 (Hybrid Retrieval)\n"
        "- Cohere Rerank API\n"
        "- Groq Cloud LLM (tu dong chon model)\n"
        "- HuggingFace Inference API (Embeddings)\n"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ──────────────────────────────────────────────────────────────────────────────
# CAU HINH CORS
# Cho phep Streamlit (localhost:8501) goi API nay tu trinh duyet.
# ──────────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",   # Streamlit local
        "http://127.0.0.1:8501",
        "https://*.streamlit.app", # Streamlit Cloud (khi deploy)
        "*",                       # Mo rong cho dev (nen thu hep khi len prod)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# DANG KY ROUTER
# ──────────────────────────────────────────────────────────────────────────────

# Tat ca endpoint duoc dinh nghia trong routes.py
# deu co prefix /api/v1 (vi du: /api/v1/health, /api/v1/ask)
app.include_router(router, prefix="/api/v1")


# ──────────────────────────────────────────────────────────────────────────────
# REDIRECT GOC / VE DOCS
# ──────────────────────────────────────────────────────────────────────────────

from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
def root():
    """Chuyen huong trang chu sang Swagger UI."""
    return RedirectResponse(url="/docs")


# ──────────────────────────────────────────────────────────────────────────────
# CHAY TRUC TIEP (python app/api/main.py)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("=" * 60, flush=True)
    print("[SERVER] Khoi dong ArXiv Agentic RAG API...", flush=True)
    print("[SERVER] Swagger UI : http://localhost:8000/docs", flush=True)
    print("[SERVER] ReDoc      : http://localhost:8000/redoc", flush=True)
    print("=" * 60, flush=True)

    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,         # Tu dong reload khi sua code
        reload_dirs=[str(BASE_DIR / "app")],
        log_level="info",
    )
