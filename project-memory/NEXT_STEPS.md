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

**Toàn bộ scaffold Phase 2 đã verify thật (không còn credential nào thiếu):**
- [x] `db/schema.sql` — đã chạy trên Supabase, 4 bảng `papers`/`sections`/`chunks`/`paper_cards` đã tồn tại thật, pgvector extension đã bật.
- [x] `app/storage/repository.py` — **verify bằng cách gọi thật**: `upsert_paper`/`get_paper`/`delete_paper`/`insert_sections`/`insert_chunks` chạy đúng trên DB thật, FK `section_pk` đúng, FTS tự sinh đúng, embedding lưu đúng 768-dim. 3 bug môi trường đã tìm+sửa trong lúc test (xem `FIXED_BUGS.md` #8-#10: IPv6-only DNS, password có `@`, pgvector ở schema `extensions`).
- [x] `app/indexing/embeddings.py` — **verify bằng cách gọi thật**: `embed_query`/`embed_documents` trả đúng 768-dim, cosine similarity đúng hướng (relevant 0.7555 > irrelevant 0.5828), xác nhận task_type bất đối xứng hoạt động đúng.
- [x] `app/config.py` thêm `database_url`; dọn `upstash_redis_url`/`upstash_redis_token` (chưa từng dùng, đúng quyết định đã ghi ở ROADMAP mục 1)
- [x] `requirements.txt` thêm `asyncpg`, `pgvector`, `tenacity`

**Cố ý CHƯA làm (rủi ro viết sai mà không test được, hoặc đợi bước trước xong):**
- [ ] Hàm hybrid search (dense+sparse trong Postgres) — giờ có DB thật rồi, có thể viết + test được, ưu tiên làm tiếp theo
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
