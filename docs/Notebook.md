# HỆ THỐNG ARXIV AGENTIC RAG

Tài liệu này tổng hợp toàn bộ lý thuyết và nguyên lý hoạt động của các module code đã được nghiên cứu trong hệ thống.
---

## 1. Module Cấu Hình & Quản Lý Môi Trường (`app/config.py`)

### 1.1. Bản chất bài toán
Một hệ thống RAG xử lý nhiều nguồn dữ liệu (PDF, vector database, model weights) cần một điểm quản trị cấu hình tập trung (Single Source of Truth) đảm bảo:
- **Tính khả chuyển môi trường (Cross-platform Portability):** Hoạt động nhất quán bất kể chạy trên macOS, Linux (Docker/Cloud) hay Windows mà không bị gãy vỡ đường dẫn file.
- **Cô lập tài nguyên (Resource Isolation):** Các thư viện như HuggingFace Hub hay Ollama mặc định lưu weights vào thư mục Home hệ thống (`~/.cache`), gây nguy cơ làm cạn kiệt dung lượng phân vùng hệ điều hành.

### 1.2. Nguyên lý logic hoạt động
- **Cơ chế Resolve đường dẫn động:**
  - Sử dụng module chuẩn `pathlib.Path(__file__).resolve().parent.parent` để tính toán động vị trí thư mục gốc (`BASE_DIR`).
  - Mọi đường dẫn con (`data`, `cache`, `chroma_db`) đều được suy dẫn tương đối từ `BASE_DIR`, giúp hệ thống tự động nhận diện đúng phân cách thư mục (`/` trên Unix/macOS, `\` trên Windows).
- **Kỹ thuật ghi đè biến môi trường hệ thống:**
  - Can thiệp trực tiếp vào `os.environ["HF_HOME"]` và `os.environ["OLLAMA_MODELS"]` trỏ về thư mục `cache/` cục bộ ngay trước khi các thư viện AI được nạp vào bộ nhớ.
  - Tắt cảnh báo symlink trên các hệ thống tệp không hỗ trợ symlink không cần quyền quản trị viên.
- **Mô hình Pydantic BaseSettings:**
  - Sử dụng cơ chế nạp khai báo (declarative loading) tự động ánh xạ các khóa trong file `.env` vào các trường dữ liệu kiểu tĩnh (type-annotated attributes).
  - Tự động gán giá trị mặc định an toàn cho các siêu tham số chunking (`chunk_size = 800`, `chunk_overlap = 150`) và tên mô hình embedding/LLM.
- **Mô hình Singleton khởi tạo sẵn:**
  - Khởi tạo đối tượng `settings = Settings()` dùng chung toàn ứng dụng, đồng thời kích hoạt tự động việc tạo các thư mục lưu trữ (`mkdir(parents=True, exist_ok=True)`).

### 1.3. Cập nhật Phase 2 (2026-09-20): thêm `database_url`, bỏ `upstash_redis_*`
- **Vì sao thêm:** Phase 2 chuyển toàn bộ storage sang Postgres (Supabase) — cần 1 connection string (`DATABASE_URL`) để `app/storage/repository.py` khởi tạo connection pool.
- **Vì sao bỏ `upstash_redis_url`/`upstash_redis_token`:** hai field này được khai báo từ đầu dự án (dự định dùng Upstash Redis làm "Memory tầng 2" cho chat history) nhưng **chưa từng có code nào import/dùng tới** — kiểm chứng bằng `grep -rn "upstash" --include="*.py" .` chỉ ra đúng 2 dòng trong `config.py`, không có nơi nào khác gọi tới. Việc lưu chat history giữa các phiên/redeploy giờ được giải quyết bằng LangGraph checkpointer trên chính Postgres (`AsyncPostgresSaver`, đang là việc dở dang — hiện tạm dùng `AsyncSqliteSaver`), nên hướng dùng Redis riêng biệt không còn cần thiết. Bài học: cấu hình "phòng khi cần" mà không có code dùng tới là nợ kỹ thuật (technical debt) âm thầm — nên xoá ngay khi phát hiện, đừng để "biết đâu sau này dùng".

---

## 2. Module Trích Xuất Văn Bản Khoa Học Thành MarkDown (`app/ingestion/parser.py`)

### 2.1. Bản chất bài toán
Bài báo khoa học định dạng PDF sở hữu cấu trúc thị phức tạp:
- **Bố cục đa cột (Multi-column / Two-column layout):** Đọc văn bản thô theo dòng quét ngang sẽ làm trộn lẫn câu chữ giữa hai cột song song.
- **Chứa các thành phần phi văn bản có cấu trúc cao:** Bảng biểu (Tables), công thức toán học (LaTeX Math), và hệ thống tiêu đề phân cấp đa tầng (H1, H2, H3).
- **Nguy cơ cạn kiệt bộ nhớ (OOM - Out of Memory):** Các engine bóc tách PDF chuyên sâu cho LLM thường tiêu tốn nhiều RAM, dễ gây crash tiến trình trên máy chủ tài nguyên giới hạn.

### 2.2. Nguyên lý logic hoạt động
- **Chiến lược chuyển đổi Markdown:**
  - Markdown giữ lại nguyên vẹn hệ thống phân cấp (`#`, `##`), cú pháp bảng biểu (`|---|`) và khối công thức (`$...$`), cung cấp đầy đủ tín hiệu ngữ nghĩa (semantic signals) cho các bước chunking và LLM reasoning phía sau.
- **Tầng xử lý chính (`pymupdf4llm`):**
  - Tự động phân tích luồng đọc để ghép nối văn bản theo đúng thứ tự logic của các cột, bóc tách cấu trúc bảng sang dạng Markdown table.
- **Cơ chế Dự phòng Đa tầng (Resilient Fallback Pattern):**
  - **Lớp 1 (Ưu tiên cao - Rich Parsing):** Thực thi `pymupdf4llm.to_markdown()`.
  - **Lớp 2 (Dự phòng khẩn cấp - Lightweight Fallback):** Nếu lớp 1 gặp ngoại lệ (tràn RAM hoặc lỗi engine), hệ thống tự động kích hoạt `fitz.open()` (PyMuPDF Core thuần túy chỉ tiêu thụ ~15MB RAM) để đọc text thô từng trang, bảo toàn sự ổn định của hệ thống mà không làm sập tiến trình.
- **Cơ chế Xác thực Tính Toàn Vẹn (Integrity Verification):**
  - Kiểm tra kết quả sau bóc tách; nếu văn bản rỗng hoặc chỉ chứa khoảng trắng (dấu hiệu của file hỏng hoặc tài liệu thuần ảnh scan), hệ thống chủ động ném ngoại lệ rõ ràng thay vì đẩy dữ liệu rỗng sang pipeline kế tiếp.

### 2.3. Cập nhật (Phase 1, bug đã sửa): `page_chunks=True` và kiểu dữ liệu trả về
- **Vấn đề phát hiện:** `pymupdf4llm.to_markdown(path, page_chunks=True)` không trả về `str` như hàm cũ giả định, mà trả về `list[dict]` — mỗi phần tử là 1 trang, gồm `text`, `metadata`, `toc_items`, `images`, `tables`. Code cũ gọi thẳng `len(md_text)` trên kết quả này sẽ ném `TypeError` ở bước regex phía sau.
- **Vì sao vẫn cố dùng `page_chunks=True` thay vì bỏ đi:** tham số này là con đường duy nhất để lấy được thông tin **số trang** đi kèm mỗi đoạn văn bản — cần cho việc trích dẫn chính xác trang PDF sau này (`page_num`, đã có cột trong schema Postgres nhưng **chưa được điền dữ liệu thật** — xem mục 2.4).
- **Cách sửa:** nối các trang lại thành 1 chuỗi Markdown duy nhất (giữ tương thích với `chunker.py` phía sau, vốn xử lý theo `str`), nhưng chèn marker `<!-- page:N -->` giữa mỗi trang để **giữ lại thông tin số trang trong chính văn bản**, không đánh mất nó ngay từ bước parse.

### 2.4. Việc còn dang dở: chunking chưa "page-aware"
Marker `<!-- page:N -->` đã có trong Markdown, nhưng `chunker.py` (module 3) **chưa được sửa để đọc marker này** và gán `page_num` cho từng `ChildChunk`. Vì vậy cột `page_num` trong bảng `chunks` (Postgres) hiện luôn là `NULL`. Đây là lý do kỹ thuật cụ thể (không phải "chưa có thời gian" chung chung): việc trích page_num đòi hỏi `split_parent_sections()` và `create_child_chunks()` phải theo dõi vị trí ký tự đang xử lý nằm giữa 2 marker nào — một thay đổi cấu trúc dữ liệu (không chỉ thêm 1 dòng code), nên được để lại thành 1 việc riêng thay vì làm vội trong lúc cutover Postgres.

---

## 3. Module Phân Mảnh Văn Bản Thông Minh (`app/ingestion/chunker.py`)

### 3.1. Bản chất bài toán
- Trong kỹ thuật RAG truyền thống (Naive RAG), việc cắt văn bản theo kích thước ký tự cố định tạo ra hiện tượng **Mất Ngữ Cảnh (Context Loss)**: Một đoạn văn bị tách rời khỏi tiêu đề chương mục của nó, khiến mô hình không xác định được nội dung đó là phát hiện mới của tác giả hay chỉ là tài liệu tham khảo từ nghiên cứu cũ.
- Việc cắt mù quáng cũng gây ra hiện tượng **Chẻ đôi từ ngữ (Word Fragmentation)** và **Xé nát bảng số liệu (Table Corruption)**, làm suy giảm nghiêm trọng độ chính xác của Vector Embedding.

### 3.2. Nguyên lý logic hoạt động
Module giải quyết bài toán bằng kiến trúc **Section-Based Parent-Child Chunking**:

```text
Markdown Document
       │
       ▼  [split_parent_sections]
┌─────────────────────────────────────────────────────────┐
│ ParentSection: Ngữ cảnh vĩ mô (Abstract, Method, ...)   │
└─────────────────────────────────────────────────────────┘
       │
       ▼  [create_child_chunks (Sliding Window)]
┌────────────────────────────────────────────────────────────────────────┐
│ ChildChunk: Ngữ cảnh vi mô (~số chars được set up, mang nhãn parent)   │
└────────────────────────────────────────────────────────────────────────┘
```

#### A. Tầng Phân Tách Cấu Trúc Parent (`ParentSection`)
- **Dynamic Heading Detection:**
  - Áp dụng hệ thống Regular Expressions đa hình thái để bắt được cả tiêu đề Markdown (`#`), tiêu đề in đậm (`**...**`), và chuẩn đánh số La Mã IEEE (`I. INTRODUCTION`).
  - Tự động tách phần mở đầu trước tiêu đề đầu tiên để lưu trữ thông tin tác giả, viện nghiên cứu (`Header`).
- **Heading Normalization:**
  - Loại bỏ ký tự định dạng thừa (`#`, `*`, `_`), tách các phần mô tả phụ dài dòng sau dấu phân cách (`—`, `:`), giới hạn độ dài nhãn danh mục để làm siêu dữ liệu (metadata) gọn gàng.
- **Heuristic Noise Filtering:**
  - Loại bỏ các phân đoạn có tên quá ngắn (< 3 ký tự) hoặc dung lượng nội dung quá nhỏ (< 30 ký tự) để triệt tiêu các đoạn rác do bắt nhầm công thức hay số trang.

#### B. Tầng Phân Mảnh (`ChildChunk`)
- **Cơ chế Cửa sổ trượt (Sliding Window with Overlap):**
  - Giữ nguyên các Section có độ dài nhỏ hơn hoặc bằng `max_chars` (800 ký tự) nhằm tránh làm vụn văn bản ngắn.
  - Với các Section lớn, thuật toán sliding window từng bước với `overlap_chars` (150 ký tự) giữa hai chunk liên tiếp để duy trì tính liên tục của ngữ nghĩa.
- **Thuật toán Cắt Theo Ranh Giới (`_find_split_point`):**
  - Thuật toán tìm kiếm lùi (backward search) trong các cửa sổ với các ưu tiên:
    1. Ưu tiên 1: Lùi tìm dấu xuống dòng đôi `\n\n` (ranh giới đoạn văn hoàn chỉnh).
    2. Ưu tiên 2: Lùi tìm dấu chấm câu `.`, `!`, `?` (ranh giới câu trọn vẹn ý).
    3. Ưu tiên 3: Lùi tìm dấu khoảng trắng (ranh giới từ ngữ, không chẻ đôi từ).
    4. Fallback: Cắt cứng tại giới hạn nếu không phát hiện khoảng trắng.
- **Cơ chế Căn chỉnh Ranh giới từ (Snap to Word Boundary):**
  - Khi con trỏ lùi lại `overlap_chars` để bắt đầu chunk mới, nếu điểm rơi nằm ở giữa một từ, con trỏ sẽ tự động dịch chuyển tiến đến khoảng trắng kế tiếp, đảm bảo chunk luôn mở đầu bằng một từ trọn vẹn.
- **Gắn cờ Bảng biểu chuyên biệt (`is_table`):**
  - Quét cấu trúc cú pháp bảng (`|...|` và `|---|`) để gán nhãn `is_table = True`, hỗ trợ bộ định tuyến (Router/Agent) ưu tiên các chunk bảng khi xử lý các truy vấn tra cứu số liệu thực nghiệm.

#### C. Cơ chế Đóng gói & Lưu trữ Trung gian (Serialization Cache) — ĐÃ NGƯNG DÙNG ở Phase 2
- Thiết kế ban đầu (Phase 1): các `ChildChunk` được đóng gói thành tệp JSON lưu tại `data/chunks_cache/{paper_id}_chunks.json`, cho phép các tầng tiếp theo (ChromaDB Vector Store và BM25 Lexical Index) tái nạp dữ liệu tức thì mà không cần parse lại PDF.
- **Vì sao ngưng dùng ở Phase 2:** cơ chế cache này **chỉ lưu `ChildChunk`, không lưu `ParentSection`** — một khiếm khuyết tồn tại từ đầu (xem mục 3.3). Khi Phase 2 bắt đầu **thật sự lưu `ParentSection` vào Postgres** (bảng `sections`), nếu vẫn dùng cache cũ thì lần upload nào trúng cache sẽ ghi `sections` rỗng, phá vỡ liên kết `chunks.section_pk`. Giải pháp chọn ở Phase 2: bỏ hẳn bước kiểm tra cache trong `routes.py`, luôn parse lại từ đầu. Đánh đổi: chậm hơn khi test lặp lại cùng 1 PDF, nhưng loại bỏ hẳn 1 lớp lỗi tiềm ẩn thay vì vá thêm 1 cơ chế cache mới cho `ParentSection`.

### 3.3. Cập nhật (Phase 1, bug đã sửa): fallback cắt vị trí sai trong `_find_split_point`
- **Vấn đề phát hiện:** nhánh fallback thứ 3 (tìm khoảng trắng) viết `space_pos = min(50, int(target * 0.08))` — đây là một **con số tính toán cố định**, không phải kết quả của việc tìm kiếm trong văn bản (`str.rfind`). Hậu quả: khi rơi vào nhánh này, vị trí cắt gần như luôn nằm ở **đầu chuỗi** (do phép `min(50, ...)` gần như luôn chọn ra một số nhỏ) chứ không phải gần vị trí mục tiêu (`target`) như 2 nhánh ưu tiên trước.
- **Bài học về đọc code:** lỗi này rất dễ bị bỏ sót khi đọc lướt vì cấu trúc code (if/return) trông "hợp lý" — chỉ lộ ra khi viết test cụ thể kiểm tra **vị trí cắt thực tế** so với `target`, không chỉ kiểm tra "hàm có chạy không". Đã thêm test hồi quy (`tests/test_chunker.py::test_fallback_space_is_near_target_not_near_start`) để đảm bảo không tái phát.
- **Cách sửa:** `text.rfind(" ", int(target * 0.08), target)` — tìm khoảng trắng thật sự gần `target`, đúng tinh thần của 2 nhánh ưu tiên trước đó.

---

## 4. Module Lưu Trữ & Tìm Kiếm — Phase 1 (`app/indexing/vector_store.py`, `bm25_store.py`) — LỊCH SỬ, đã thay bằng Postgres ở mục 4.4

> Mục 4.1–4.3 mô tả thiết kế Phase 1 (ChromaDB + BM25). Hai file này **không còn được dùng** kể từ Phase 2 (2026-09-20) và đã bị xoá hẳn khỏi repo (2026-09-27, xem `project-memory/FIXED_BUGS.md`). Đọc để hiểu **vì sao ban đầu chọn thiết kế đó** và **vì sao sau này thay đổi** — bản thân lý do thay đổi cũng là kiến thức đáng học.

### 4.1. Bản chất bài toán
- **Giới hạn của Lexical Search (Tìm kiếm từ khóa thuần túy):** Khi người dùng đặt câu hỏi bằng ngôn ngữ tự nhiên, từ vựng sử dụng thường không trùng khớp 100% với từ ngữ trong tài liệu khoa học (ví dụ: *"mô hình xử lý ảnh"* vs *"Visual feature extraction using Convolutional layers"*). Kỹ thuật tìm kiếm chuỗi truyền thống sẽ bỏ sót các tài liệu mang tính đồng nghĩa hoặc tương đương ngữ cảnh.
- **Giới hạn ngược lại của Semantic Search (Tìm kiếm ngữ nghĩa thuần túy):** embedding vector giỏi bắt "ý nghĩa gần giống" nhưng lại kém chính xác với **từ khoá/số liệu đặc thù** (tên biến, tên mô hình viết tắt, con số thí nghiệm) — đây là lý do hệ thống dùng **Hybrid Search** (kết hợp cả hai) thay vì chỉ chọn 1 trong 2, không phải chỉ vì "làm cho đủ bộ".
- **Thách thức tài nguyên khi triển khai (Resource Bottleneck):** Việc nạp trực tiếp mô hình Embedding cục bộ (như PyTorch / `sentence-transformers`) vào bộ nhớ làm tiêu tốn từ 500MB đến 1GB RAM, dễ dẫn đến lỗi Out-Of-Memory (OOM) trên các môi trường máy chủ tài nguyên hạn chế (Railway, Render, Streamlit Cloud) hoặc lỗi tràn tệp hoán trang (Paging file) trên hệ điều hành.

### 4.2. Nguyên lý logic hoạt động (Dense — ChromaDB)

```text
ChildChunks ──► HuggingFace Inference API (all-MiniLM-L6-v2) ──► 384D Embeddings ──► ChromaDB (data/chroma_db/)
                                                                                           ▲
User Query  ──► HuggingFace Inference API                   ──► Query Vector    ───────────┘
                                                                (Cosine Similarity Search: Top 20)
```

- **Chiến lược Embedding "0MB RAM" qua HuggingFace Inference API:** lớp `HuggingFaceAPIEmbeddings` tuân thủ giao diện chuẩn LangChain (`embed_documents`, `embed_query`), uỷ thác toàn bộ tính toán ma trận embedding cho hạ tầng đám mây HuggingFace qua `InferenceClient.feature_extraction()` — máy chủ cục bộ tiêu thụ 0MB RAM cho model weights. `EMBED_BATCH_SIZE = 64` giúp giảm số round-trip mạng.
- **Quản trị ChromaDB (`VectorStoreManager`):** lưu bền vững tại `data/chroma_db/`; dùng song song `langchain_chroma.Chroma` (tìm kiếm ngữ nghĩa tích hợp sẵn) và `chromadb.PersistentClient` nguyên bản (thao tác quản trị: đếm vector, xoá collection).
- **Cách ly Phân vùng (Isolated Partition Retrieval):** lọc metadata cứng `{"paper_id": paper_id}` trong mọi truy vấn — mỗi bài báo có một "không gian tìm kiếm" cách ly hoàn toàn, tránh **ô nhiễm ngữ cảnh chéo** giữa các bài báo khác nhau đã nạp trước đó. Nhưng đây **không phải partition thật** (physical partition) — chỉ là 1 collection ChromaDB duy nhất (`arxiv_papers`) lọc bằng metadata, nghĩa là mọi paper chia sẻ chung 1 không gian index vật lý.

### 4.2b. Nguyên lý logic hoạt động (Sparse — BM25)
- **Thuật toán BM25 (Best Matching 25):** biến thể cải tiến của TF-IDF, tính điểm liên quan dựa trên tần suất từ khoá xuất hiện trong văn bản (Term Frequency) có điều chỉnh theo độ dài văn bản và độ hiếm của từ trong toàn bộ kho ngữ liệu (Inverse Document Frequency) — bắt chính xác 100% các từ khoá/số liệu/thuật ngữ mà dense embedding có thể bỏ sót.
- **Tokenizer chuyên biệt:** regex `[a-zA-Z0-9]+(?:[._\-][a-zA-Z0-9]+)*` giữ nguyên các thuật ngữ khoa học ghép bằng dấu chấm/gạch nối (`CortexODE`, `0.939`, `state-of-the-art`) làm 1 token duy nhất thay vì tách vụn, đồng thời loại token quá ngắn (< 2 ký tự, ít mang thông tin).
- **Lưu trữ:** index `BM25Okapi` + metadata được ghi xuống 2 file pickle (`data/bm25_index/bm25.pkl`, `chunks_meta.pkl`) — đây chính là nguồn gốc của lỗ hổng bảo mật/ổn định "unsafe pickle load" và rủi ro không tương thích phiên bản thư viện, 1 trong các lý do khiến Phase 2 thay bằng cột `tsvector` ngay trong Postgres.

### 4.3. Bug đã sửa (Phase 1): BM25 xoá sạch dữ liệu paper cũ khi upload paper mới
- **Nguyên nhân gốc rễ:** `BM25StoreManager.build_index()` **luôn build lại từ đầu** (`self._chunks_meta = []`) chỉ từ danh sách chunks của paper **đang được upload**, trong khi ChromaDB (dense) là index **cộng dồn** (mỗi upload chỉ thêm, không xoá gì). Hai hệ thống lưu trữ tách rời nhau về mặt vòng đời dữ liệu (lifecycle) là nguồn gốc sâu xa của bug này — không phải do code sai một dòng, mà do **kiến trúc 2 store độc lập** vốn đã tiềm ẩn nguy cơ lệch pha.
- **Hậu quả:** sau khi upload paper B, mọi truy vấn hybrid search cho paper A đã upload trước đó sẽ **âm thầm tụt về dense-only** (sparse luôn trả rỗng cho paper A) — không có exception, không có log lỗi, chỉ là chất lượng tìm kiếm giảm mà không ai nhận ra nếu không kiểm tra kỹ.
- **Cách vá (Phase 1, tạm thời):** merge theo `chunk_id` với corpus đã load sẵn từ đĩa lúc khởi tạo `BM25StoreManager()`, thay vì reset về rỗng.
- **Cách giải quyết triệt để (Phase 2):** không vá thêm nữa — **loại bỏ hẳn khái niệm "2 store tách rời"**. Khi sparse index chỉ là 1 cột (`fts tsvector`) trong cùng 1 bảng `chunks` với dense (`embedding vector`), được ghi trong cùng 1 câu `INSERT`/transaction, thì lớp lỗi "2 store lệch pha nhau" **biến mất về mặt cấu trúc** — không còn 2 nơi lưu trữ để có thể lệch pha nữa. Đây là ví dụ cụ thể cho nguyên tắc: khi 1 bug lặp đi lặp lại xuất phát từ 1 quyết định kiến trúc, cách sửa bền vững là đổi kiến trúc, không phải vá thêm logic.

### 4.4. Cập nhật Phase 2 (2026-09-20): chuyển sang Postgres (Supabase) + pgvector + Full-Text Search

**Vì sao chuyển, không chỉ "để hiện đại hơn":**
1. **Persistence thật sự:** ChromaDB + pickle BM25 đều lưu trên đĩa cục bộ của container Railway — đĩa này bị xoá sạch mỗi lần redeploy. Một Postgres managed (Supabase) là dịch vụ độc lập với vòng đời container, dữ liệu sống sót qua redeploy.
2. **Gộp 2 store thành 1 để loại bỏ hẳn lớp bug ở mục 4.3**, đã giải thích ở trên.
3. **`ParentSection` lần đầu tiên được lưu thật** (bảng `sections`), giải quyết luôn vấn đề nêu ở mục 3 rằng "parent-child chunking" trước đây chỉ có tên gọi, không có hành vi.

**Kiến trúc mới, các khái niệm cần nắm:**
- **pgvector:** extension Postgres bổ sung kiểu dữ liệu `vector(N)` và các toán tử khoảng cách (`<=>` cho cosine distance, `<->` cho Euclidean, `<#>` cho inner product). Chỉ mục **HNSW** (Hierarchical Navigable Small World) được dùng thay vì brute-force scan — đánh đổi 1 chút độ chính xác (approximate nearest neighbor) để lấy tốc độ truy vấn gần như hằng số bất kể số lượng vector.
- **Postgres Full-Text Search (thay BM25):** cột `fts tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED` — Postgres **tự động tính lại** cột này mỗi khi `text` thay đổi, không cần code ứng dụng tự quản lý đồng bộ. Truy vấn qua `websearch_to_tsquery()` (cú pháp giống công cụ tìm kiếm web: từ cách nhau = AND ngầm định, `OR` viết hoa = OR, ngoặc kép = tìm cụm từ chính xác) rồi xếp hạng bằng `ts_rank_cd()`.
  - **Giới hạn cần biết:** `websearch_to_tsquery` yêu cầu **AND ngầm định** giữa các từ sau khi loại stopword — với câu hỏi tự nhiên dài ("What is the Dice coefficient of CortexODE?"), nếu 1 đoạn chỉ chứa "Dice" mà không có "coefficient" nằm gần đó, đoạn đó sẽ **không match**, dù về mặt ngữ nghĩa vẫn liên quan. Đây là hạn chế mang tính thiết kế của FTS (tối ưu cho tìm từ khoá chính xác, không phải cho câu hỏi tự nhiên) — không phải bug, nhưng là 1 lý do khiến Phase 3 (eval harness) cần đo đạc cụ thể chất lượng retrieval thay vì tin tưởng mù quáng.
- **asyncpg + connection pool:** thư viện driver Postgres thuần async (không có bản sync) — buộc toàn bộ pipeline retrieval phải chuyển sang `async`/`await` (xem mục 9.3). Pool kết nối được khởi tạo **lazy** (chỉ tạo khi lần đầu cần dùng) và **cache lại dùng chung** cho các lần gọi sau (singleton pattern) — quan trọng vì mở/đóng kết nối Postgres liên tục cho mỗi query sẽ rất chậm.
- **pgvector Python package (`pgvector.asyncpg`):** dạy `asyncpg` cách chuyển đổi qua lại giữa `list[float]` (Python) và kiểu `vector` (Postgres) — gọi là "codec". **Bài học thực chiến:** Supabase cài extension `pgvector` vào schema `extensions`, không phải `public` như mặc định của thư viện — nếu không truyền `schema="extensions"` khi đăng ký codec, sẽ gặp lỗi `unknown type: public.vector` dù extension đã bật và bảng đã tạo đúng. Loại lỗi này chỉ phát hiện được khi **chạy thật với Postgres thật**, không thể tìm ra bằng đọc code hay unit test không cần mạng.

**RRF (Reciprocal Rank Fusion) — không đổi thuật toán, chỉ đổi nguồn dữ liệu đầu vào:**
- Công thức: với mỗi tài liệu xuất hiện trong 1 hay nhiều danh sách xếp hạng, điểm số = tổng của `1 / (k + rank)` trên từng danh sách nó xuất hiện (hằng số `k = 60` theo bài báo gốc của Cormack et al., 2009 — giá trị này làm giảm ảnh hưởng của các vị trí top quá cao, tránh 1 danh sách "áp đảo" danh sách còn lại).
- **Vì sao tái dùng nguyên hàm cũ (`reciprocal_rank_fusion()`) thay vì viết lại bằng SQL:** thuật toán RRF chỉ cần đầu vào là 2 danh sách `{chunk_id, rank}` — nó **không quan tâm** rank đó đến từ BM25 hay Postgres FTS, từ ChromaDB hay pgvector. Tách biệt "thuật toán fusion" khỏi "nguồn dữ liệu" là 1 ví dụ cụ thể của nguyên tắc thiết kế phần mềm tốt: hàm càng ít giả định về nguồn gốc dữ liệu đầu vào, càng dễ tái sử dụng khi hạ tầng thay đổi.
- Trong Postgres, dense và sparse là **2 câu SQL riêng biệt** chạy song song bằng `asyncio.gather()` (không phải 1 câu SQL hybrid duy nhất) — đơn giản hơn để viết đúng và test được, và tận dụng lại được code Python đã kiểm chứng.

---

## 5. Module Chấm Điểm Lại (`app/indexing/reranker.py`)

### 5.1. Bản chất bài toán
- Hybrid search (dense + sparse + RRF) trả về khoảng 20 ứng viên có độ liên quan **tương đối tốt** nhưng **chưa đủ tinh** — RRF chỉ hợp nhất 2 thứ hạng, không thực sự "đọc hiểu" mối quan hệ ngữ nghĩa sâu giữa câu hỏi và từng đoạn văn.
- **Bi-encoder (dùng ở bước embedding) vs Cross-encoder (dùng ở bước rerank):** bi-encoder mã hoá câu hỏi và tài liệu **độc lập** thành 2 vector rồi so khoảng cách — nhanh (tính trước embedding tài liệu, chỉ cần encode câu hỏi lúc query) nhưng kém chính xác vì không "nhìn thấy" cả 2 cùng lúc. Cross-encoder đưa **cả cặp** (câu hỏi, tài liệu) vào cùng 1 lần forward pass qua mô hình — chính xác hơn hẳn nhưng chậm hơn nhiều lần, nên chỉ khả thi khi áp dụng lên một tập nhỏ ứng viên (top-20) thay vì toàn bộ kho dữ liệu.

### 5.2. Nguyên lý logic hoạt động
- **Chế độ kép tự động:** `RerankerManager` chọn `mode = "cohere"` nếu có `COHERE_API_KEY`, ngược lại rơi về `mode = "local"` (CrossEncoder `ms-marco-MiniLM-L-6-v2` chạy trên CPU, ~85MB). Việc chọn chế độ diễn ra **1 lần lúc khởi tạo**, không tự động chuyển đổi khi Cohere lỗi lúc runtime (rate limit, mất mạng) — đây là 1 hạn chế được ghi nhận, không phải thiết kế có chủ đích.
- **Bug đã sửa:** bản cũ tự cắt `text[:512]` theo **ký tự** trước khi đưa vào `CrossEncoder(max_length=512)` — nhưng tham số `max_length` của CrossEncoder vốn đã tự cắt theo **token** ở tầng tokenizer. Cắt theo ký tự trước làm mất tới ~60-70% nội dung 1 chunk 800 ký tự một cách không cần thiết (vì trung bình 1 token tiếng Anh ≈ 4 ký tự, 512 ký tự ≈ 128 token, trong khi mô hình cho phép tới 512 token). Cách sửa: bỏ hẳn bước cắt thủ công, để tokenizer tự lo — đúng nguyên tắc "đừng tự làm việc mà thư viện đã làm đúng sẵn".
- **Không mutate dữ liệu gốc:** bản cũ gán thêm field (`rerank_score`, `rerank_rank`) và `sort()` trực tiếp trên list `candidates` truyền vào — thay đổi luôn cả dữ liệu của hàm gọi nó (side effect ngầm, dễ gây bug khó tìm nếu hàm gọi còn dùng lại `candidates` gốc sau đó). Đã sửa để làm việc trên bản sao.

---

## 6. Module Điều Phối LLM (`app/llm/llm_factory.py`)

### 6.1. Bản chất bài toán
- Một hệ thống Agentic RAG production cần **độc lập với 1 nhà cung cấp LLM cụ thể** — API có thể bị giới hạn tốc độ (rate limit), model có thể bị ngừng hỗ trợ (decommissioned), giá có thể thay đổi. Code gọi LLM ở nhiều nơi (grade, rewrite, generate) không nên biết đang dùng Groq hay Gemini hay Ollama.

### 6.2. Nguyên lý logic hoạt động
- **Factory Pattern:** `get_llm()` là điểm vào **duy nhất** để khởi tạo LLM — không nơi nào khác trong codebase được phép import thẳng `ChatGroq`/`ChatGoogleGenerativeAI`/`ChatOllama`. Đổi provider chỉ cần sửa `.env`, không sửa code gọi.
- **Auto-detect theo API key có sẵn:** thứ tự ưu tiên Groq → Gemini → Ollama (local, không cần key, dùng khi không có key nào).
- **Tự động chọn model Groq còn hoạt động:** `_pick_best_groq_model()` gọi API `Groq().models.list()` để lấy danh sách model **thực sự đang khả dụng**, rồi chọn model đầu tiên khớp với danh sách ưu tiên đã định sẵn (nhóm GPT-OSS mới nhất trước, các bản Llama cũ hơn sau). Mục đích: tránh lỗi "model decommissioned" khi nhà cung cấp ngừng hỗ trợ 1 model — hệ thống tự thích nghi thay vì hardcode tên model có thể lỗi thời.
- **Bug đã sửa — thiếu cache:** ban đầu, mỗi lần `get_llm()` được gọi (tức mỗi lần 1 node LangGraph chạy: grade, rewrite, generate) đều gọi lại `models.list()` — tốn 1 round-trip mạng thừa cho **mỗi bước** của **mỗi câu hỏi**. Sửa bằng `@lru_cache` — cache theo tham số đầu vào, chỉ gọi API thật 1 lần trong suốt vòng đời process.
- **Bug đã sửa — fallback không hoạt động:** dù có cấu hình cả `GROQ_API_KEY` lẫn `GEMINI_API_KEY`, code cũ **chỉ chọn tĩnh 1 provider lúc khởi tạo** — nếu Groq lỗi lúc đang chạy (429 rate limit, timeout), toàn bộ request thất bại thay vì tự chuyển sang Gemini. Sửa bằng `.with_fallbacks([gemini_llm])` — một cơ chế có sẵn của LangChain Runnable: khi provider được **tự động chọn** là Groq và có sẵn Gemini key, LLM trả về sẽ tự thử Gemini nếu lời gọi Groq thất bại lúc `.invoke()`/`.ainvoke()`, hoàn toàn trong suốt với code gọi nó.

---

## 7. Kỹ Thuật Corrective-RAG & Prompt Templates (`app/llm/prompt_templates.py`, tư duy đằng sau `app/agent/rag_graph.py`)

### 7.1. Bản chất bài toán
- **Naive RAG** (retrieve rồi generate thẳng) có 1 điểm yếu cố hữu: nếu retrieval trả về tài liệu không đủ liên quan (do câu hỏi mơ hồ, do hạn chế của thuật toán tìm kiếm), LLM vẫn cố "generate" một câu trả lời — dẫn tới **hallucination** (bịa thông tin) hoặc trả lời sai mà tự tin.
- **Corrective RAG (CRAG)** — Yan et al., 2024 — thêm 1 bước tự đánh giá (self-reflection): sau khi retrieve, một LLM riêng biệt (hoặc cùng LLM, prompt khác) **chấm điểm** xem tài liệu lấy được có đủ để trả lời hay không, trước khi cho phép bước generate chạy.

### 7.2. Nguyên lý logic hoạt động — vòng lặp 3 bước
```
retrieve → grade → [đủ?] → generate
              │
              └─[không đủ, còn lượt]→ rewrite → retrieve (lặp lại)
```
- **`GRADE_DOCS_TEMPLATE`:** yêu cầu LLM trả lời **chỉ** "yes"/"no" — dùng chỉ dẫn "Be strict" để tránh LLM quá dễ dãi (chấm "yes" dù tài liệu chỉ liên quan mơ hồ). Hạn chế hiện tại: chấm điểm **cả batch tài liệu cùng lúc**, không chấm từng tài liệu riêng — nghĩa là không biết chính xác tài liệu nào trong 5 tài liệu là "thừa" hay "thiếu".
- **`REWRITE_QUERY_TEMPLATE`:** viết lại câu hỏi rõ ràng, cụ thể hơn (mở rộng viết tắt, thêm thuật ngữ kỹ thuật) khi grade trả "no". Hạn chế hiện tại: chỉ nhận `{question}` làm đầu vào, **không biết** tài liệu vừa lấy được là gì hay vì sao bị chấm "không đủ" — việc viết lại diễn ra "mù", không có phản hồi cụ thể để cải thiện.
- **Giới hạn số lần thử lại (`MAX_REWRITES = 2`):** tránh vòng lặp vô hạn nếu câu hỏi thực sự không thể trả lời được từ tài liệu hiện có — sau 2 lần rewrite không thành công, hệ thống vẫn generate với dữ liệu tốt nhất đang có, chấp nhận khả năng trả lời "không tìm thấy thông tin" còn hơn là treo vô thời hạn.
- **`RAG_ANSWER_TEMPLATE`:** ràng buộc rõ "chỉ trả lời dựa trên context được cung cấp", có câu trả lời mặc định khi thiếu thông tin ("I cannot find sufficient information...") — đây chính là cơ chế khiến hệ thống **từ chối trả lời một cách an toàn** thay vì bịa số liệu, như đã quan sát thực tế khi test Phase 2 với câu hỏi về 1 số liệu cụ thể nằm trong bảng mà retrieval không lấy trúng (xem mục 9.4) — đó là hành vi **đúng theo thiết kế**, không phải lỗi.

---

## 8. Module Agent Điều Phối (`app/agent/rag_graph.py`) — LangGraph StateGraph

### 8.1. Bản chất bài toán
- Vòng lặp Corrective-RAG ở mục 7 có **trạng thái thay đổi qua nhiều bước** (câu hỏi có thể bị viết lại, số lần rewrite tăng dần, danh sách tài liệu thay đổi) và **luồng điều khiển có điều kiện** (đi tiếp "generate" hay quay lại "rewrite" tuỳ kết quả chấm điểm) — viết bằng code tuần tự (if/else lồng nhau, gọi hàm liên tiếp) sẽ nhanh chóng trở nên khó đọc và khó mở rộng khi thêm bước mới.

### 8.2. Nguyên lý logic hoạt động
- **StateGraph:** LangGraph mô hình hoá agent như 1 đồ thị hữu hạn trạng thái — mỗi **node** là 1 hàm nhận `AgentState` (a `TypedDict`) và trả về phần trạng thái cần cập nhật; mỗi **edge** định nghĩa node nào chạy tiếp theo. `add_conditional_edges()` cho phép rẽ nhánh dựa trên 1 hàm điều kiện (`decide_after_grade`) đọc trạng thái hiện tại.
- **`Annotated[list, add_messages]`:** LangGraph cho phép định nghĩa cách 1 field trong state được **cập nhật** (thay vì ghi đè) — `add_messages` là reducer có sẵn, tự động **nối thêm** tin nhắn mới vào danh sách cũ thay vì thay thế toàn bộ, giúp lịch sử hội thoại tích luỹ qua nhiều lượt gọi `ask()` mà không cần code thủ công.
- **Checkpointer — bộ nhớ giữa các lượt hỏi:** LangGraph tách biệt "trạng thái của 1 lần chạy graph" (ephemeral) khỏi "lịch sử hội thoại giữa nhiều lần chạy" (persistent) — checkpointer (`SqliteSaver`/`AsyncSqliteSaver`/`AsyncPostgresSaver`) chịu trách nhiệm lưu/đọc phần sau, định danh bằng `thread_id`. Cùng 1 `thread_id`, agent "nhớ" được các câu hỏi/trả lời trước đó mà không cần code gọi tự truyền lại lịch sử.
- **Bug đã sửa — thiếu dependency `langgraph-checkpoint-sqlite`:** package cung cấp `SqliteSaver`/`AsyncSqliteSaver` chưa từng được khai báo trong `requirements.txt`. Đoạn code khởi tạo checkpointer có `except Exception` **quá rộng** — bắt luôn cả `ModuleNotFoundError` (thiếu thư viện) và âm thầm fallback về `MemorySaver`/`InMemorySaver` (bộ nhớ chỉ tồn tại trong RAM của tiến trình). Hậu quả: lịch sử chat bị mất **mỗi khi restart process**, không chỉ khi redeploy — 1 bug nghiêm trọng hơn nhiều so với những gì log thể hiện, vì log vẫn hiện "[SUCCESS]" ở nhánh fallback. **Bài học:** `except Exception` bao trùm quá nhiều loại lỗi khác nhau (lỗi cấu hình, lỗi thiếu thư viện, lỗi runtime) khiến hệ thống "trông như hoạt động" trong khi thực chất đang chạy ở chế độ suy giảm (degraded mode) không ai nhận ra — nên bắt lỗi cụ thể (`ModuleNotFoundError` riêng, lỗi kết nối riêng) thay vì gộp chung.

### 8.3. Cập nhật Phase 2: chuyển toàn bộ sang `async`
- **Vì sao bắt buộc, không phải tuỳ chọn:** `asyncpg` (driver Postgres dùng ở `repository.py`) **chỉ hỗ trợ async**, không có bản đồng bộ (sync). Muốn gọi hàm async từ 1 node đồng bộ, cách "nhanh" là bọc bằng `asyncio.run()` — nhưng cách này **vỡ connection pool**: pool được cache lại (singleton) và gắn chặt với 1 event loop cụ thể; mỗi lần gọi `asyncio.run()` tạo ra 1 event loop **mới** rồi huỷ đi ngay sau đó, khiến lần gọi thứ 2 cố dùng lại pool cũ sẽ gặp lỗi "attached to a different loop". Đây là lý do kỹ thuật cụ thể buộc phải đổi **toàn bộ chuỗi gọi hàm** (mọi node, hàm `ask()`, route FastAPI `/ask`) sang async nhất quán, chứ không thể chỉ đổi 1 điểm.
- **LangChain Runnable hỗ trợ cả 2 chế độ sẵn:** may mắn là các `chain = prompt | llm` (LCEL — LangChain Expression Language) đã tự hỗ trợ cả `.invoke()` (sync) lẫn `.ainvoke()` (async) mà không cần viết lại logic — chỉ cần đổi lời gọi.
- **Checkpointer cũng phải đổi theo:** `SqliteSaver` (sync) không tương thích với graph chạy async — phải đổi sang `AsyncSqliteSaver` (dùng `aiosqlite` thay vì `sqlite3` chuẩn). `aiosqlite` mặc định bật **WAL mode** (Write-Ahead Logging) — sinh thêm 2 file sidecar (`chat_memory.db-shm`, `chat_memory.db-wal`) mà bản sync trước đó không có, cần thêm vào `.gitignore`.
- **Singleton lazy-async cho graph đã compile:** không thể compile graph kèm checkpointer async ngay lúc import module (vì cần `await` để mở kết nối, mà top-level code của 1 module Python không async được) — giải pháp là compile **lazily**, lần đầu tiên `ask()` được gọi thật (cùng pattern với `repository.get_pool()`), rồi cache lại dùng chung cho các lần gọi sau.

### 8.4. Quan sát thực tế Phase 2: từ chối trả lời đúng cách không phải bug
Khi test với câu hỏi tra số liệu cụ thể ("Dice coefficient là bao nhiêu?") mà số liệu đó nằm trong 1 bảng dữ liệu, hệ thống trả `grade: "no"` và từ chối trả lời thay vì bịa số. Điều tra cho thấy: chunk chứa số liệu đúng có thứ hạng dense-search #11-13 (không lọt top-5 sau rerank), và sparse search (Postgres FTS) chỉ khớp 2/3 chunk có chứa từ "dice" do yêu cầu AND ngầm định với các từ khác trong câu hỏi (xem mục 4.4). Đây là **giới hạn thật của chất lượng retrieval** với nội dung dạng bảng — không phải lỗi wiring hay bug logic — và là bằng chứng cụ thể cho việc vì sao ROADMAP đặt "Phase 3: Eval harness" (đo Recall@k, nDCG có hệ thống) làm bước tiếp theo, thay vì tiếp tục đoán mò chỗ nào cần cải thiện.

---

## 9. Tầng API & Frontend (`app/api/routes.py`, `streamlit_app.py`)

### 9.1. Bản chất bài toán
- Tầng API là ranh giới giữa "logic nghiệp vụ" (ingestion, retrieval, agent) và "giao tiếp mạng" (HTTP) — cần định nghĩa rõ hợp đồng dữ liệu (request/response schema) để frontend và backend phát triển độc lập nhau mà vẫn tương thích.

### 9.2. Nguyên lý logic hoạt động
- **FastAPI + Pydantic schemas:** mỗi endpoint khai báo `response_model` tường minh (`UploadResponse`, `AskResponse`, ...) — FastAPI tự validate dữ liệu đầu vào/đầu ra, tự sinh tài liệu Swagger UI (`/docs`) mà không cần viết thêm code.
- **Bug đã sửa — `sources` luôn rỗng:** route `/ask` đọc `result.get("documents")` — key này **không tồn tại** trong `AgentState` (thực tế field lưu tài liệu lấy được tên là `retrieved_chunks`, và là `list[dict]` chứ không phải LangChain `Document` object). Vì `dict.get()` trả `None`/`[]` thay vì ném lỗi khi key không tồn tại, bug này **không hiện lỗi ở đâu cả** — UI chỉ đơn giản không bao giờ hiển thị được nguồn trích dẫn, một dạng lỗi "âm thầm" nguy hiểm hơn lỗi gây crash vì không ai chú ý cho đến khi cố tình kiểm tra.
- **Cập nhật Phase 2:** `/upload` giờ gọi thẳng `repository.upsert_paper/insert_sections/insert_chunks` (Postgres) thay vì `VectorStoreManager`/`BM25StoreManager`/ghi JSON; `/papers` đọc từ Postgres; `/ask` kiểm tra paper tồn tại qua Postgres thay vì dict registry trong bộ nhớ. Toàn bộ route liên quan đổi thành `async def` cho khớp với `repository.py`/`rag_graph.ask()` async.
- **Streamlit frontend (`streamlit_app.py`):** giao tiếp với backend **thuần qua HTTP** (không import trực tiếp code Python của backend) — cho phép 2 phần triển khai độc lập (Railway cho API, Streamlit Cloud cho UI). `_resolve_api_base()` tự chọn địa chỉ API theo thứ tự: biến môi trường → `st.secrets` → mặc định `localhost:8000` — giúp code chạy được cả lúc dev cục bộ lẫn lúc đã deploy mà không cần sửa code.

---

## 10. Kiến Thức Nền Cho Các Bước Tiếp Theo (chưa triển khai, ghi chú trước để tham khảo)

- **RAPTOR (Sarthi et al., ICLR 2024):** xây cây tóm tắt đệ quy — gom nhóm các chunk có nội dung tương tự (bằng clustering như GMM/UMAP trên embedding), dùng LLM tóm tắt từng nhóm thành 1 "chunk cấp cao hơn", lặp lại nhiều tầng. Giải quyết lớp câu hỏi tổng quan ("đóng góp chính của bài báo là gì?") mà retrieval theo chunk lẻ tẻ luôn yếu.
- **GraphRAG — vì sao KHÔNG làm:** trích xuất entity + quan hệ thành đồ thị tri thức, tốn rất nhiều lời gọi LLM để xây dựng và cần rebuild khi có tài liệu mới — không phù hợp ngân sách free-tier với quy mô vài trăm bài báo. Thay thế bằng 1 bảng quan hệ (`paper_facts`) trích xuất có cấu trúc qua 1 lượt LLM duy nhất — đạt phần lớn lợi ích (trả lời câu hỏi dạng "paper nào dùng X trên dataset Y?" bằng SQL, chính xác 100%) với chi phí thấp hơn nhiều.
- **Multi-paper routing (Phase 4):** mỗi paper có 1 "paper card" (tóm tắt + embedding riêng, bảng `paper_cards` đã có sẵn trong schema nhưng chưa dùng) — khi câu hỏi cần so sánh nhiều paper, 1 bước "router" sẽ chọn ra top-N paper liên quan trước, rồi **fan-out** retrieval riêng cho từng paper (không gộp chung 1 lượt tìm kiếm toàn cục) để tránh kết quả bị thiên lệch về phía 1 paper có nhiều chunk hơn.
