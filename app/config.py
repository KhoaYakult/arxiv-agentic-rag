"""
app/config.py
==============
Quản lý cấu hình toàn bộ hệ thống và cache/database lưu trữ trên ổ D.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Đường dẫn thư mục gốc dự án: D:\Project\arxiv-agentic-rag
BASE_DIR = Path(__file__).resolve().parent.parent

# Thư mục cache cô lập hoàn toàn trên ổ D
CACHE_DIR = BASE_DIR / "cache"
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
    data_dir: Path = BASE_DIR / "data"                 # Thư mục lưu file bài báo PDF
    db_dir: Path = BASE_DIR / "data" / "chroma_db"    # Thư mục chứa cơ sở dữ liệu Vector

    # ── CẤU HÌNH EMBEDDING & LLM ──
    embedding_model_name: str = "all-MiniLM-L6-v2"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_llm_model: str = "qwen2.5:1.5b"
    groq_model_name: str = "llama3-70b-8192"


    # ── CẤU HÌNH CHUNKING ──
    chunk_size: int = 800    # Kích thước tối đa mỗi chunk tính theo ký tự (characters)
    chunk_overlap: int = 150 # Số ký tự gối đầu (overlap) giữa 2 chunk liên tiếp

    # ── API KEYS ──
    cohere_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    hf_token: str = ""       

    # Upstash Redis: Cloud Memory API 
    upstash_redis_url: str = ""
    upstash_redis_token: str = ""

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

# Tự động tạo các thư mục dữ liệu trên ổ D 
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.db_dir.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print("=" * 60)
    print("  XAC NHAN CAU HINH DU AN (ISOLATED ON DRIVE D)")
    print("=" * 60)
    print(f"  - Base Dir    : {settings.base_dir}")
    print(f"  - Data Dir    : {settings.data_dir}")
    print(f"  - Chroma DB   : {settings.db_dir}")
    print(f"  - HF Cache    : {os.environ.get('HF_HOME')}")
    print(f"  - Ollama Cache: {os.environ.get('OLLAMA_MODELS')}")
    print(f"  - HF Token    : {'Da cai dat' if settings.hf_token else 'Chua cai dat'}")
    print("=" * 60)
