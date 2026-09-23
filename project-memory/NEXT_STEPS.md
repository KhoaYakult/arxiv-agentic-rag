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

**Cutover HOÀN TẤT — verify thật end-to-end qua HTTP (2026-09-20):**
- [x] `repository.hybrid_search()` — dense (pgvector `<=>`) + sparse (Postgres FTS `websearch_to_tsquery`) chạy song song (`asyncio.gather`), gộp bằng `reciprocal_rank_fusion()` **tái dùng nguyên** từ Phase 1.
- [x] `rag_graph.py` chuyển toàn bộ sang **async** (`retrieve_node`/`grade_node`/`rewrite_node`/`generate_node`, `ask()`), checkpointer đổi `SqliteSaver` → `AsyncSqliteSaver` (vẫn SQLite, chỉ đổi sync→async — `AsyncPostgresSaver` là bước riêng sau). Lý do bắt buộc đổi async: `asyncpg` chỉ hỗ trợ async, dùng `asyncio.run()` chắp vá trong node sync sẽ làm vỡ connection pool giữa các lần gọi (pool cache bị gắn với event loop cũ đã đóng).
- [x] `routes.py`: `/upload` ghi thẳng vào Postgres (`repository.upsert_paper`/`insert_sections`/`insert_chunks`), `/papers` đọc từ Postgres, `/ask` gọi `ask()` async — xoá hẳn `_load_registry`/`_save_registry`/`papers_registry.json`. **Không dùng cache JSON chunk cũ nữa** (cache đó không lưu `ParentSection`, sẽ mất section khi cache-hit) — mỗi upload parse lại từ đầu.
- [x] Test thật qua HTTP (uvicorn thật, không mock): upload PDF 182 chunks thật → `/ask` 2 câu hỏi (1 câu tổng quát → `grade:"yes"`, câu trả lời đúng, 5 sources hợp lý; 1 câu hỏi số liệu cụ thể trong bảng → `grade:"no"`, đúng vì retrieval không tìm ra đúng ô bảng chứa số — **hành vi an toàn đúng, không phải bug**, ghi nhận là backlog Phase 3). `/papers` phản ánh đúng dữ liệu Postgres. Dọn sạch dữ liệu test sau đó.
- [x] Bug #11 (xem `FIXED_BUGS.md`): Gemini free tier quota tính theo **số embedding/phút** chứ không phải số HTTP call — `embed_documents()` giờ tự throttle 61s giữa các batch >100 text.
- [x] `.gitignore`: thêm `data/chat_memory.db-shm`/`-wal` (sidecar file mới do `AsyncSqliteSaver`/`aiosqlite` dùng WAL mode, sync `sqlite3` cũ không sinh ra 2 file này).

**`/upload` → BackgroundTasks HOÀN TẤT — verify thật qua HTTP (2026-09-23):**
- [x] `POST /upload` giờ tách 2 phần: đồng bộ (validate + lưu file + `upsert_paper(status="processing")`) trả **202** gần như tức thì; phần chậm (`process_paper_ingestion` + embed + `insert_sections`/`insert_chunks` + `set_paper_status`) chạy trong `_process_and_index_paper()` qua FastAPI `BackgroundTasks`. Lỗi trong task nền bị bắt và ghi `status="failed"` (không raise — không còn request nào để nhận HTTPException).
- [x] Thêm `GET /papers/{paper_id}/status` (`PaperStatusResponse`: `paper_id`/`title`/`status`/`num_chunks`) để client poll.
- [x] `repository.list_papers()` đổi query thêm `WHERE status = 'ready'` — đây là **fix đúng theo docstring cũ** ("đã index thành công"), không phải feature mới: trước đây `/upload` đồng bộ nên client không bao giờ thấy được paper `processing`; giờ có khoảng thời gian thật paper ở trạng thái đó, nếu không lọc thì dropdown Streamlit sẽ cho chọn paper rỗng.
- [x] `streamlit_app.py`: `upload_pdf()` đổi kỳ vọng `201`→`202`; thêm `poll_paper_status()` (poll 2s/lần, timeout 600s) — nút "Upload & Index" giờ hiện 2 spinner nối tiếp (gửi file → đợi index nền) thay vì 1 spinner chờ response đồng bộ như cũ.
- [x] Verify thật qua HTTP (uvicorn thật, port 8010): upload PDF 182 chunks → `202` trả về ngay lập tức (không block) → status `processing` → `/papers` list rỗng đúng lúc đang xử lý → sau ~10s status chuyển `ready`, `num_chunks=182` → `/papers` hiện đúng → `/ask` trả lời đúng với 5 sources. Dọn sạch dữ liệu test (`repository.delete_paper`) sau đó.

**`DELETE /papers/{id}` + `lifespan` HOÀN TẤT — verify thật qua HTTP (2026-09-23):**
- [x] `DELETE /papers/{paper_id}` — CASCADE qua FK có sẵn, xoá thêm file PDF trên đĩa, `204` khi thành công, `404` idempotent khi gọi lại. Verify cả trường hợp xoá lúc paper đang `processing` (background task fail an toàn ở bước insert, không crash).
- [x] `app/api/main.py` thêm `lifespan` (`asynccontextmanager`) gọi `repository.close_pool()` lúc shutdown.
- [x] **Bug #12 tìm được + sửa trong lúc verify:** `/upload` lưu PDF theo tên file gốc thay vì `paper_id` → 2 paper trùng tên file ghi đè nhau trên đĩa → đã làm mất file mẫu `data/sample_test_cortexODE.pdf` (không phục hồi được, gitignored). Đã sửa: cả `/upload` và `DELETE` dùng `f"{paper_id}.pdf"`. **`data/` hiện không còn PDF mẫu nào — cần upload 1 PDF thật trước khi test tay.**

**Cố ý CHƯA làm:**
- [ ] **Xoá hẳn** `app/indexing/vector_store.py`, `app/indexing/bm25_store.py`, `app/indexing/hybrid_retriever.py` — đã KHÔNG còn được routes.py/rag_graph.py dùng nữa (cutover xong), nhưng cố ý giữ lại code cũ thêm 1 nhịp phòng khi cần rollback nhanh. Xoá ở bước sau khi user xác nhận ổn định.
- [ ] Checkpointer → `AsyncPostgresSaver` thật (đang tạm dùng `AsyncSqliteSaver`, vẫn SQLite - chat history vẫn mất khi Railway redeploy, chưa xong hoàn toàn theo ROADMAP)
- [ ] `ChildChunk` thêm `page_num`/`char_start`/`char_end`/`level` + `chunker.py` xử lý page-aware (`insert_chunks()` hiện ghi NULL cho các cột này)
- [ ] File dedup qua `file_hash` (cột đã có trong schema, `get_paper_by_hash()` đã viết trong repository.py, nhưng `/upload` chưa gọi tới)

## Sau Phase 2 (tóm tắt — chi tiết ở `docs/ROADMAP.md`)

- [ ] **Phase 3** — Eval harness (Recall@k, nDCG@10, RAGAS) + chỉ tối ưu retrieval khi có số đo, không đoán
- [ ] **Phase 4** — Multi-paper query router + fan-out retrieval xuyên nhiều paper
- [ ] **Phase 5** — RAPTOR + structured knowledge layer (`paper_facts`)
- [ ] **Phase 6** — Production polish (auth, rate limit, streaming, Streamlit refactor, Langfuse)

## Quyết định đang treo (chưa cần làm ngay, nhưng đừng quên)

- User được hỏi có muốn cài skill `superpowers` (bộ 14 skill từ plugin cùng tên) hay không — **đã từ chối** vì thấy phức tạp hơn cài plugin thật. Nếu sau này muốn dùng, hướng đơn giản nhất là chạy `/plugin install superpowers@superpowers-dev` trong terminal Claude Code thật (không phải qua Bash/VSCode extension session) — marketplace `superpowers-dev` đã có sẵn trong `~/.claude/plugins/known_marketplaces.json` trên máy user.
