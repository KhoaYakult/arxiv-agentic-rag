"""
app/config.py
==============
Quản lý cấu hình toàn bộ hệ thống và cache/database lưu trữ trên ổ D.
"""

import contextlib
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Đường dẫn thư mục gốc dự án: D:\Project\arxiv-agentic-rag
BASE_DIR = Path(__file__).resolve().parent.parent

# Tren Vercel (env VERCEL=1) filesystem cua function la read-only, chi /tmp ghi duoc
# (va /tmp chi song trong vong doi 1 instance) - nen data/cache chuyen sang /tmp.
IS_VERCEL = bool(os.environ.get("VERCEL"))
DEFAULT_DATA_DIR = Path("/tmp/data") if IS_VERCEL else BASE_DIR / "data"

# Thư mục cache cô lập hoàn toàn trên ổ D
CACHE_DIR = Path("/tmp/cache") if IS_VERCEL else BASE_DIR / "cache"
with contextlib.suppress(OSError):  # filesystem read-only (serverless): cache khong bat buoc
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Ghi đè biến môi trường hệ thống để HuggingFace và Ollama không lưu vào ổ C (C:\Users\HP\...)
os.environ["HF_HOME"] = str(CACHE_DIR / "huggingface")
os.environ["OLLAMA_MODELS"] = str(CACHE_DIR / "ollama")

# Tắt cảnh báo symlinks trên Windows (không cần Developer Mode / Admin)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

class Settings(BaseSettings):
    """Cấu hình ứng dụng với Pydantic BaseSettings"""

    # ── ĐƯỜNG DẪN ──
    base_dir: Path = BASE_DIR                          # Thư mục gốc dự án
    data_dir: Path = DEFAULT_DATA_DIR                  # Thư mục lưu file bài báo PDF (env DATA_DIR ghi de)

    # ── CẤU HÌNH EMBEDDING & LLM ──
    ollama_llm_model: str = "qwen2.5:1.5b"
    groq_model_name: str = "llama3-70b-8192"
    # gemini-2.0-flash da bi Google tat 2026-06-01; 2.5-flash-lite tra 404 voi key moi -> dung 3.5-flash-lite (da goi thuc te OK 2026-10-24)
    gemini_model_name: str = "gemini-3.5-flash-lite"


    # ── CẤU HÌNH CHUNKING ──
    chunk_size: int = 800    # Kích thước tối đa mỗi chunk tính theo ký tự (characters)
    chunk_overlap: int = 150 # Số ký tự gối đầu (overlap) giữa 2 chunk liên tiếp

    # ── API KEYS ──
    cohere_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    hf_token: str = ""

    # ── PHASE 2: SUPABASE POSTGRES (app/storage/repository.py) ──
    # Connection string dang: postgresql://postgres:[PASSWORD]@...supabase.co:5432/postgres
    # Lay tu Supabase: Project -> Connect -> URI. Rong = repository.py chua dung duoc.
    database_url: str = ""

    # ── DEPLOY CONG KHAI (Vercel) ──
    # Gioi han upload 4 MB: Vercel cat request body o 4.5 MB. File lon hon -> dung
    # POST /papers/arxiv (server tu tai PDF tu arxiv.org, khong qua body request).
    max_upload_mb: float = 4.0
    # Rong = khong bat auth. Co gia tri = moi route /api/v1 (tru /health, /health/db)
    # phai gui header X-API-Key bang dung gia tri nay.
    app_api_key: str = ""
    # Danh sach origin duoc phep goi API tu trinh duyet, phan tach bang dau phay.
    allowed_origins: str = "http://localhost:8501,http://127.0.0.1:8501"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Khởi tạo instance cấu hình dùng chung toàn ứng dụng
settings = Settings()

# Truyền HF_TOKEN vào môi trường nếu đã được cấu hình trong .env
# → tắt cảnh báo "unauthenticated requests" từ HuggingFace Hub
if settings.hf_token:
    os.environ["HF_TOKEN"] = settings.hf_token

# Tự động tạo các thư mục dữ liệu trên ổ D (bo qua neu filesystem read-only)
with contextlib.suppress(OSError):
    settings.data_dir.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print("=" * 60)
    print("  XAC NHAN CAU HINH DU AN (ISOLATED ON DRIVE D)")
    print("=" * 60)
    print(f"  - Base Dir    : {settings.base_dir}")
    print(f"  - Data Dir    : {settings.data_dir}")
    print(f"  - HF Cache    : {os.environ.get('HF_HOME')}")
    print(f"  - Ollama Cache: {os.environ.get('OLLAMA_MODELS')}")
    print(f"  - HF Token    : {'Da cai dat' if settings.hf_token else 'Chua cai dat'}")
    print("=" * 60)
