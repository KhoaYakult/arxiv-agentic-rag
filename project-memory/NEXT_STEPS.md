# Next Steps

> Cập nhật: 2026-09-19 · Xem `STATE.md` để biết vì sao đang kẹt ở đây.

## Ngay trước mắt (đang chờ user)

1. [ ] User mở Docker Desktop trên máy Mac, chạy `docker info` để confirm daemon sống.
2. [ ] User chạy `docker build -t arxiv-rag .` (đừng quên dấu `.`), rồi `docker run` với `$PORT` tuỳ chỉnh + `docker ps` check `healthy`.
3. [ ] User upload PDF thật + gọi `/ask` thật, xác nhận `sources` trong response khác rỗng.
4. [ ] Sau khi (2) và (3) OK → push 8 commit lên `origin` (hiện `main` đang `ahead 8`, chưa push).

Khi cả 4 mục trên xong → **Phase 1 đóng hẳn**, chuyển Phase 2.

## Phase 2 — Supabase là nguồn sự thật duy nhất ⭐ (phase quan trọng nhất)

Chi tiết đầy đủ + schema SQL ở `docs/ROADMAP.md`. Tóm tắt việc cần làm:

- [ ] Tạo schema Postgres: `papers`, `sections`, `chunks` (thêm `page_num`, `char_start/end`, `level`, `embedding vector(768)`, `fts tsvector`), `paper_cards`
- [ ] Viết `app/storage/repository.py` thay `_load_registry()`/`VectorStoreManager`/`BM25StoreManager`
- [ ] **Xoá hẳn** `app/indexing/vector_store.py` và `app/indexing/bm25_store.py` (không phải archive/comment-out — xoá thật, đã có Postgres thay thế)
- [ ] `EmbeddingProvider` mới dùng Gemini `gemini-embedding-001` (768-dim), có retry/backoff (dùng `tenacity`)
- [ ] `/upload` chuyển sang `BackgroundTasks`, trả `202` + endpoint polling status
- [ ] Thêm `DELETE /papers/{id}`; dense+sparse chạy song song (`asyncio.gather`); singleton retriever qua FastAPI `lifespan`
- [ ] Checkpointer SQLite → `AsyncPostgresSaver` (dùng `langgraph-checkpoint-postgres`, không phải sqlite nữa)

## Sau Phase 2 (tóm tắt — chi tiết ở `docs/ROADMAP.md`)

- [ ] **Phase 3** — Eval harness (Recall@k, nDCG@10, RAGAS) + chỉ tối ưu retrieval khi có số đo, không đoán
- [ ] **Phase 4** — Multi-paper query router + fan-out retrieval xuyên nhiều paper
- [ ] **Phase 5** — RAPTOR + structured knowledge layer (`paper_facts`)
- [ ] **Phase 6** — Production polish (auth, rate limit, streaming, Streamlit refactor, Langfuse)

## Quyết định đang treo (chưa cần làm ngay, nhưng đừng quên)

- User được hỏi có muốn cài skill `superpowers` (bộ 14 skill từ plugin cùng tên) hay không — **đã từ chối** vì thấy phức tạp hơn cài plugin thật. Nếu sau này muốn dùng, hướng đơn giản nhất là chạy `/plugin install superpowers@superpowers-dev` trong terminal Claude Code thật (không phải qua Bash/VSCode extension session) — marketplace `superpowers-dev` đã có sẵn trong `~/.claude/plugins/known_marketplaces.json` trên máy user.
