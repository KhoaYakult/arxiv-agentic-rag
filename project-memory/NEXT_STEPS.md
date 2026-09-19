# Next Steps

> Cập nhật: 2026-09-19 · Phase 1 đã verify xong hết (xem `STATE.md`).

## Ngay trước mắt

1. [x] Docker build/run/healthcheck/non-root/$PORT — verify xong trên máy user.
2. [x] Upload + `/ask` thật, `sources` khác rỗng — verify xong.
3. [ ] Hỏi user có muốn push 10 commit lên `origin` không (`main` đang `ahead 10`) — đừng tự ý push, hỏi trước.
4. [ ] Nhắc user dọn container test trên máy họ nếu chưa: `docker stop arxiv-rag-test && docker rm arxiv-rag-test`.

Khi (3) xong → **Phase 1 đóng hẳn hoàn toàn**, bắt đầu Phase 2.

## Phase 2 — Supabase là nguồn sự thật duy nhất ⭐ (phase quan trọng nhất)

Chi tiết đầy đủ + schema SQL ở `docs/ROADMAP.md`.

**Đang chờ 2 credential từ user (cả hai đều rỗng trong `.env`):**
- [ ] `DATABASE_URL` — user đang tạo Supabase project (hướng dẫn đã đưa trong chat).
- [ ] `GEMINI_API_KEY` — cần key thật để test `app/indexing/embeddings.py` (hiện chỉ verify được lúc raise lỗi khi thiếu key, chưa gọi API thật).

**Đã scaffold xong (code viết được, nhưng CHƯA test được với DB/API thật, và CHƯA wire vào routes.py — pipeline Phase 1 vẫn là pipeline đang chạy thật):**
- [x] `db/schema.sql` — DDL đầy đủ cho `papers`/`sections`/`chunks`/`paper_cards` (chạy qua Supabase SQL Editor)
- [x] `app/indexing/embeddings.py` — `GeminiEmbeddingProvider` (768-dim MRL truncation, task_type bất đối xứng RETRIEVAL_DOCUMENT/QUERY, retry qua tenacity), factory `get_embedding_provider()`
- [x] `app/storage/repository.py` — connection pool (asyncpg + pgvector codec), CRUD cho `papers`/`sections`/`chunks` (upsert_paper, insert_sections, insert_chunks, get_paper, list_papers, delete_paper, get_paper_by_hash để dedup)
- [x] `app/config.py` thêm `database_url`; dọn `upstash_redis_url`/`upstash_redis_token` (chưa từng dùng, đúng quyết định đã ghi ở ROADMAP mục 1)
- [x] `requirements.txt` thêm `asyncpg`, `pgvector`, `tenacity`

**Cố ý CHƯA làm hôm nay (rủi ro viết sai mà không test được):**
- [ ] Hàm hybrid search (dense+sparse trong Postgres) — đợi có DB thật để chạy thử, không viết SQL phức tạp "mù"
- [ ] Wire `repository.py`/`embeddings.py` vào `routes.py`/`hybrid_retriever.py`
- [ ] **Xoá hẳn** `app/indexing/vector_store.py` và `app/indexing/bm25_store.py` (chỉ xoá sau khi cutover xong và test lại end-to-end như Phase 1)
- [ ] `/upload` chuyển sang `BackgroundTasks`, trả `202` + endpoint polling status
- [ ] `DELETE /papers/{id}`; dense+sparse chạy song song (`asyncio.gather`); singleton retriever qua FastAPI `lifespan`
- [ ] Checkpointer SQLite → `AsyncPostgresSaver` (dùng `langgraph-checkpoint-postgres`, chưa thêm dependency này vội)
- [ ] `ChildChunk` thêm `page_num`/`char_start`/`char_end`/`level` + `chunker.py` xử lý page-aware (việc riêng, `insert_chunks()` hiện ghi NULL cho các cột này)

## Sau Phase 2 (tóm tắt — chi tiết ở `docs/ROADMAP.md`)

- [ ] **Phase 3** — Eval harness (Recall@k, nDCG@10, RAGAS) + chỉ tối ưu retrieval khi có số đo, không đoán
- [ ] **Phase 4** — Multi-paper query router + fan-out retrieval xuyên nhiều paper
- [ ] **Phase 5** — RAPTOR + structured knowledge layer (`paper_facts`)
- [ ] **Phase 6** — Production polish (auth, rate limit, streaming, Streamlit refactor, Langfuse)

## Quyết định đang treo (chưa cần làm ngay, nhưng đừng quên)

- User được hỏi có muốn cài skill `superpowers` (bộ 14 skill từ plugin cùng tên) hay không — **đã từ chối** vì thấy phức tạp hơn cài plugin thật. Nếu sau này muốn dùng, hướng đơn giản nhất là chạy `/plugin install superpowers@superpowers-dev` trong terminal Claude Code thật (không phải qua Bash/VSCode extension session) — marketplace `superpowers-dev` đã có sẵn trong `~/.claude/plugins/known_marketplaces.json` trên máy user.
