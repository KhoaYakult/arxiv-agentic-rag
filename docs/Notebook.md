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

#### C. Cơ chế Đóng gói & Lưu trữ Trung gian (Serialization Cache)
- Các `ChildChunk` được đóng gói thành tệp JSON lưu tại `data/chunks_cache/{paper_id}_chunks.json`.
- Cho phép các tầng tiếp theo (ChromaDB Vector Store và BM25 Lexical Index) có thể tái nạp dữ liệu tức thì mà không cần phải thực hiện lại chu trình parse PDF và chunking tốn kém tài nguyên tính toán.

---

## 4. Module Lưu Trữ & Tìm Kiếm Ngữ Nghĩa Dense Vector (`app/indexing/vector_store.py`)

### 4.1. Bản chất bài toán
- **Giới hạn của Lexical Search (Tìm kiếm từ khóa thuần túy):** Khi người dùng đặt câu hỏi bằng ngôn ngữ tự nhiên, từ vựng sử dụng thường không trùng khớp 100% với từ ngữ trong tài liệu khoa học (ví dụ: *"mô hình xử lý ảnh"* vs *"Visual feature extraction using Convolutional layers"*). Kỹ thuật tìm kiếm chuỗi truyền thống sẽ bỏ sót các tài liệu mang tính đồng nghĩa hoặc tương đương ngữ cảnh.
- **Thách thức tài nguyên khi triển khai (Resource Bottleneck):** Việc nạp trực tiếp mô hình Embedding cục bộ (như PyTorch / `sentence-transformers`) vào bộ nhớ làm tiêu tốn từ 500MB đến 1GB RAM, dễ dẫn đến lỗi Out-Of-Memory (OOM) trên các môi trường máy chủ tài nguyên hạn chế (Railway, Render, Streamlit Cloud) hoặc lỗi tràn tệp hoán trang (Paging file) trên hệ điều hành.

### 4.2. Nguyên lý logic hoạt động

```text
ChildChunks ──► HuggingFace Inference API (all-MiniLM-L6-v2) ──► 384D Embeddings ──► ChromaDB (data/chroma_db/)
                                                                                           ▲
User Query  ──► HuggingFace Inference API                   ──► Query Vector    ───────────┘
                                                                (Cosine Similarity Search: Top 20)
```

#### A. Chiến lược Embedding "0MB RAM" qua HuggingFace Inference API
- Thiết kế lớp tùy biến `HuggingFaceAPIEmbeddings` tuân thủ giao diện chuẩn của LangChain (`embed_documents`, `embed_query`).
- Toàn bộ tác vụ tính toán ma trận embedding được ủy thác cho hạ tầng đám mây của Hugging Face Hub thông qua `InferenceClient.feature_extraction()`, giúp máy chủ cục bộ **tiêu thụ 0MB RAM** cho model weights.
- **Xử lý theo lô (Batch Processing):** Cấu hình `EMBED_BATCH_SIZE = 64` giúp tăng tốc độ truyền tải mạng gấp nhiều lần so với gửi từng request đơn lẻ, đồng thời không vượt ngưỡng giới hạn payload của HTTP API.
- **Chuẩn hóa chiều Tensor:** Tự động phát hiện và ép phẳng (flatten / mean pooling) nếu API trả về tensor 3D, đảm bảo ma trận đầu ra luôn chuẩn 2D `(batch_size, embedding_dim)` với số chiều $d = 384$.

#### B. Quản trị Cơ sở dữ liệu Vector ChromaDB (`VectorStoreManager`)
- **Lưu trữ bền vững (Persistent Storage):** Toàn bộ cơ sở dữ liệu vector được ghi vào thư mục `data/chroma_db/` trên đĩa cứng, duy trì trạng thái dữ liệu ngay cả khi ứng dụng khởi động lại.
- **Mô hình kết nối kép (Dual-client Architecture):**
  - Dùng `langchain_chroma.Chroma` để tận dụng hàm tìm kiếm ngữ nghĩa tích hợp sẵn trong hệ sinh thái LangChain.
  - Dùng song song `chromadb.PersistentClient` nguyên bản để thực hiện các thao tác quản trị trực tiếp (như đếm chính xác số lượng vector `col.count()`, hoặc xóa sạch collection cũ mà không gặp lỗi cache lock).

#### C. Cơ chế Truy vấn Cách ly Phân vùng (Isolated Partition Retrieval)
- Trong phương thức `similarity_search`, áp dụng bộ lọc siêu dữ liệu cứng:
  $$\text{search\_filter} = \{\text{"paper\_id"}: \text{paper\_id}\}$$
- **Mục đích:** Khi người dùng tra cứu một bài báo cụ thể, không gian tìm kiếm vector bị giới hạn tuyệt đối trong phạm vi bài báo đó. Điều này triệt tiêu hoàn toàn hiện tượng **ô nhiễm ngữ cảnh chéo (Cross-document Contamination)** từ các bài báo khác đã nạp trước đó trong cơ sở dữ liệu.
- Mặc định trả về **Top 20 ứng viên (`top_k = 20`)** để tạo ra một tập ứng viên dồi dào, đủ phong phú cho bước Cohere Reranker ở phía sau chấm điểm chọn lọc lại.


