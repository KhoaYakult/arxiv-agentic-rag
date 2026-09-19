# Next Steps

> Cập nhật: 2026-09-19 · Phase 1 đã verify xong hết (xem `STATE.md`).

## Ngay trước mắt

1. [x] Docker build/run/healthcheck/non-root/$PORT — verify xong trên máy user.
2. [x] Upload + `/ask` thật, `sources` khác rỗng — verify xong.
3. [ ] Hỏi user có muốn push 10 commit lên `origin` không (`main` đang `ahead 10`) — đừng tự ý push, hỏi trước.
4. [ ] Nhắc user dọn container test trên máy họ nếu chưa: `docker stop arxiv-rag-test && docker rm arxiv-rag-test`.

Khi (3) xong → **Phase 1 đóng hẳn hoàn toàn**, bắt đầu Phase 2.

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
