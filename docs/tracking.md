# Tracking

File theo dõi tiến độ dự án — cập nhật mỗi khi có thay đổi đáng kể. Chi tiết kỹ thuật/lý do quyết định xem [`ROADMAP.md`](ROADMAP.md) (kế hoạch 6 phase) và [`Architecture.md`](Architecture.md) (tài liệu hệ thống).

> **Cập nhật:** 2026-09-18 · **Đang ở:** Phase 1 (hoàn thành, chờ verify thủ công 2 mục) → chuẩn bị Phase 2

---

## Đã làm

### Phase 1 — Cầm máu + nền kỹ thuật

**7 bug đã sửa** (chi tiết ở `ROADMAP.md` mục 2):
- [x] Bug #1 — `parser.py`: `page_chunks=True` trả sai kiểu (`list[dict]` thay vì `str`)
- [x] Bug #2 — `chunker.py`: `_find_split_point` fallback cắt sai vị trí
- [x] Bug #3 — `routes.py`: `/ask` trả `sources` luôn rỗng (đọc sai key)
- [x] Bug #4 — `llm_factory.py`: Gemini fallback không chạy, thiếu cache, thiếu dependency
- [x] Bug #5 — `reranker.py`: cắt chunk theo ký tự thay vì để tokenizer tự xử lý
- [x] Bug #6 — `bm25_store.py`: upload paper mới xoá sạch BM25 của paper cũ (vá tạm, sẽ xoá hẳn ở Phase 2)
- [x] Bug #7 *(phát hiện thêm lúc verify)* — thiếu dependency `langgraph-checkpoint-sqlite`, khiến chat history âm thầm mất mỗi lần restart

**Hạ tầng kỹ thuật:**
- [x] `pyproject.toml` (ruff + pytest config, có ghi lý do ignore từng rule)
- [x] `tests/` — 20 unit test cho 4 hàm thuần, không cần network/API key
- [x] `.github/workflows/ci.yml` — CI chạy ruff + pytest mỗi push/PR vào `main`
- [x] `Dockerfile` — multi-stage, tôn trọng `$PORT`, non-root user, `HEALTHCHECK`
- [x] `.dockerignore`, `.pre-commit-config.yaml`, `Makefile`
- [x] `requirements.txt` pin `==` (verify trên venv sạch hoàn toàn, không chỉ venv đang dùng)
- [x] `README.md`, `CLAUDE.md`, `docs/Architecture.md` (viết mới hoàn toàn)
- [x] Dọn dẹp repo: `.gitignore` thiếu `.venv/` (1.5GB), gộp thư mục skill trùng lặp (`.agents/` vs `.claude/skills/`)

**Trạng thái git:** 7 commit trên `main`, **chưa push lên origin** (`ahead 7`).

**Chưa tự verify được (cần bạn xác nhận):**
- [ ] `docker build` + `docker run` thật — kiểm tra `$PORT` tuỳ chỉnh hoạt động, `HEALTHCHECK` báo `healthy`, chạy bằng non-root user
- [ ] Upload PDF thật → `/ask` thật — kiểm tra field `sources` trong response khác rỗng (xác nhận bug #3 hết thật trên luồng end-to-end, không chỉ unit test)

→ Hướng dẫn cụ thể đã đưa ở phiên trước; báo lại kết quả để đóng hẳn Phase 1.

---

## Tiếp theo

### Ngay trước mắt
- [ ] Bạn verify 2 mục Docker/e2e ở trên
- [ ] Push 7 commit lên origin (khi bạn xác nhận sẵn sàng)

### Phase 2 — Supabase là nguồn sự thật duy nhất ⭐ (phase quan trọng nhất, xem `ROADMAP.md`)
- [ ] Schema Postgres: `papers`, `sections`, `chunks` (thêm `page_num`, `char_start/end`, `level`, `embedding vector(768)`, `fts tsvector`), `paper_cards`
- [ ] `app/storage/repository.py` thay `_load_registry`/`VectorStoreManager`/`BM25StoreManager` → **xoá** `vector_store.py`, `bm25_store.py`
- [ ] `EmbeddingProvider` mới dùng Gemini `gemini-embedding-001` (768-dim), có retry/backoff
- [ ] `/upload` chuyển sang `BackgroundTasks`, trả `202` + polling status
- [ ] `DELETE /papers/{id}`, dense+sparse chạy song song, singleton retriever qua `lifespan`
- [ ] Checkpointer SQLite → `AsyncPostgresSaver`

### Sau Phase 2 (tóm tắt, xem `ROADMAP.md` để biết chi tiết)
- [ ] Phase 3 — Eval harness (Recall@k, nDCG@10, RAGAS) + cải thiện retrieval có số đo
- [ ] Phase 4 — Multi-paper query router + fan-out retrieval xuyên paper
- [ ] Phase 5 — RAPTOR + structured knowledge layer (`paper_facts`)
- [ ] Phase 6 — Production polish (auth, rate limit, streaming, Streamlit refactor, Langfuse)
