"""
eval/index_papers.py
=====================
Index các paper PDF trong `eval/papers/*.pdf` vào một Postgres + pgvector RIÊNG
cho đánh giá (Phase 3), bằng đúng code ingestion/embedding/repository của dự án.

DB này TUYỆT ĐỐI không phải Supabase production: script đọc URL từ biến môi trường
`EVAL_DATABASE_URL` (bắt buộc), từ chối chạy nếu URL chứa "supabase", và ghi đè
`settings.database_url` TRƯỚC KHI repository tạo pool (nên DATABASE_URL trong .env
không bao giờ được dùng).

paper_id = "arxiv-" + tên file không đuôi (vd 1706.03762.pdf -> arxiv-1706.03762).
Chạy lại rẻ: paper đã 'ready' thì bỏ qua. Giữa 2 paper cần embed, script ngủ 61s
vì quota free tier Gemini tính theo số text embed mỗi phút (100/phút).

Chạy từ thư mục gốc repo:
    docker run -d --name pgeval -e POSTGRES_PASSWORD=postgres -p 55434:5432 \\
        -v arxiv_eval_pg:/var/lib/postgresql/data pgvector/pgvector:pg16
    EVAL_DATABASE_URL=postgresql://postgres:postgres@localhost:55434/postgres \\
        python eval/index_papers.py
"""

import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import asyncpg

from app.config import settings

PAPERS_DIR = BASE_DIR / "eval" / "papers"
SCHEMA_SQL = BASE_DIR / "db" / "schema.sql"
COOLDOWN_BETWEEN_PAPERS_SEC = 61


def _get_eval_db_url() -> str:
    """Đọc + kiểm tra URL; ghi đè settings.database_url trước khi repository chạm vào."""
    url = os.environ.get("EVAL_DATABASE_URL", "").strip()
    if not url:
        sys.exit("[LOI] Chua dat EVAL_DATABASE_URL (Postgres+pgvector rieng cho eval).")
    if "supabase" in url.lower():
        sys.exit("[LOI] EVAL_DATABASE_URL tro vao Supabase - tu choi chay (DB eval phai tach rieng production).")
    settings.database_url = url
    return url


async def _prepare_database(db_url: str) -> None:
    """Dựng DB giống Supabase (y hệt tests/integration/conftest.py), idempotent."""
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS extensions")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")
        db_name = await conn.fetchval("SELECT current_database()")
        await conn.execute(f'ALTER DATABASE "{db_name}" SET search_path = public, extensions')
    finally:
        await conn.close()

    # Kết nối mới để nhận search_path mới rồi mới chạy schema.sql
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    finally:
        await conn.close()


def _guess_title(pdf_path: Path) -> str:
    """Dòng đầu tiên có nghĩa của trang 1; không đọc được thì dùng tên file."""
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            for line in doc[0].get_text().splitlines():
                line = line.strip()
                if len(line) >= 8 and any(c.isalpha() for c in line):
                    return line[:200]
    except Exception:
        pass
    return pdf_path.stem


async def _index_one(pdf_path: Path, paper_id: str) -> None:
    """Parse -> chunk -> embed -> ghi DB cho 1 paper. Ném exception nếu lỗi."""
    from app.indexing.embeddings import get_embedding_provider
    from app.ingestion.chunker import process_paper_ingestion
    from app.storage import repository

    # Dọn dữ liệu cũ (nếu lần chạy trước dở dang) để không lẫn sections/chunks mồ côi
    await repository.delete_paper(paper_id)
    await repository.upsert_paper(
        paper_id,
        title=_guess_title(pdf_path),
        filename=pdf_path.name,
        status="processing",
    )
    try:
        sections, chunks = process_paper_ingestion(pdf_path, paper_id=paper_id)
        embeddings = get_embedding_provider().embed_documents([c.text for c in chunks])
        section_pk_map = await repository.insert_sections(paper_id, sections)
        await repository.insert_chunks(paper_id, chunks, embeddings, section_pk_map)
        await repository.set_paper_status(paper_id, "ready", num_chunks=len(chunks))
    except Exception:
        await repository.set_paper_status(paper_id, "failed")
        raise


async def _summary_rows() -> list[tuple]:
    from app.storage import repository

    pool = await repository.get_pool()
    return await pool.fetch(
        """
        SELECT p.paper_id, p.status,
               (SELECT count(*) FROM sections s WHERE s.paper_id = p.paper_id) AS num_sections,
               (SELECT count(*) FROM chunks c WHERE c.paper_id = p.paper_id) AS num_chunks,
               (SELECT count(*) FROM chunks c
                 WHERE c.paper_id = p.paper_id AND c.page_num IS NULL) AS null_pages
        FROM papers p ORDER BY p.paper_id
        """
    )


async def main() -> None:
    db_url = _get_eval_db_url()
    pdfs = sorted(PAPERS_DIR.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"[LOI] Khong co PDF nao trong {PAPERS_DIR}")

    from app.storage import repository

    await _prepare_database(db_url)
    started = time.time()
    embedded_any = False
    try:
        for pdf_path in pdfs:
            paper_id = "arxiv-" + pdf_path.stem
            existing = await repository.get_paper(paper_id)
            if existing and existing["status"] == "ready":
                print(f"[SKIP] {paper_id} da 'ready' ({existing['num_chunks']} chunks)", flush=True)
                continue

            if embedded_any:
                print(
                    f"[INFO] Ngu {COOLDOWN_BETWEEN_PAPERS_SEC}s giua 2 paper de tranh quota "
                    "Gemini free-tier...",
                    flush=True,
                )
                await asyncio.sleep(COOLDOWN_BETWEEN_PAPERS_SEC)

            print(f"[INDEX] {paper_id} ({pdf_path.name})", flush=True)
            embedded_any = True
            try:
                await _index_one(pdf_path, paper_id)
            except Exception as e:
                print(f"[LOI] {paper_id} that bai: {e!r}", flush=True)
                traceback.print_exc()

        rows = await _summary_rows()
    finally:
        await repository.close_pool()

    print("\n" + "=" * 78)
    print(f"{'paper_id':<24}{'status':<10}{'sections':>10}{'chunks':>10}{'page NULL':>12}")
    print("-" * 78)
    for r in rows:
        print(
            f"{r['paper_id']:<24}{r['status']:<10}{r['num_sections']:>10}"
            f"{r['num_chunks']:>10}{r['null_pages']:>12}"
        )
    print("=" * 78)
    print(f"Tong thoi gian: {time.time() - started:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
