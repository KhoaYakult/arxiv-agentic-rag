"""
ui/streamlit_app.py
===================
Giao dien nguoi dung cho ArXiv Agentic RAG.
Giao tiep voi FastAPI Backend qua HTTP REST API.

Cach chay:
    # Terminal 1: Bat FastAPI server
    python -m uvicorn app.api.main:app --port 8000 --reload

    # Terminal 2: Bat Streamlit UI (tu thu muc goc repo)
    streamlit run ui/streamlit_app.py

QUY TAC AN TOAN: moi text khong tin cay (cau hoi, cau tra loi LLM, preview
chunk tu PDF, ten paper lay tu ten file) PHAI qua html.escape() (helper `esc`)
truoc khi chen vao chuoi HTML co unsafe_allow_html=True.
"""

import html
import json
import os
import re
import time
import uuid
from datetime import datetime

import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# CAU HINH TRANG
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="ArXiv Agentic RAG",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Cấu hình API Backend linh hoạt (mặc định localhost:8000 khi chạy local)
LOCAL_API = "http://127.0.0.1:8000"


def _resolve_api_base() -> str:
    # 1. Ưu tiên biến môi trường
    if os.environ.get("API_BASE"):
        return os.environ["API_BASE"]
    # 2. Thử lấy từ Streamlit Secrets nếu có file cấu hình
    try:
        if "API_BASE" in st.secrets:
            return st.secrets["API_BASE"]
    except Exception:
        pass
    # 3. Mặc định chạy local kết nối tới FastAPI localhost
    return LOCAL_API

API_BASE = _resolve_api_base().rstrip("/")
if not API_BASE.endswith("/api/v1"):
    API_BASE = f"{API_BASE}/api/v1"


def _resolve_api_key() -> str | None:
    """API key gui kem header X-API-Key: env APP_API_KEY -> st.secrets -> None."""
    if os.environ.get("APP_API_KEY"):
        return os.environ["APP_API_KEY"]
    try:
        if "APP_API_KEY" in st.secrets:
            return str(st.secrets["APP_API_KEY"]) or None
    except Exception:
        pass
    return None


API_KEY = _resolve_api_key()

# Gioi han phia server (app/api/routes.py) - kiem tra truoc o UI de bao loi than thien.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024
PAPER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
_ARXIV_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?/?(?:[?#].*)?$",
    re.IGNORECASE,
)
MSG_UNAUTHORIZED = (
    "API key thiếu hoặc không hợp lệ (HTTP 401). "
    "Kiểm tra biến môi trường / secret `APP_API_KEY` của giao diện."
)


def esc(text) -> str:
    """Escape text khong tin cay truoc khi chen vao HTML (chong XSS)."""
    return html.escape(str(text), quote=True)


def esc_multiline(text) -> str:
    """Escape roi doi xuong dong thanh <br> (khong sinh dong trong de khoi
    ngat HTML block cua markdown)."""
    return esc(text).replace("\r\n", "\n").replace("\n", "<br>")


def extract_arxiv_id(raw: str) -> str | None:
    """Lay arXiv ID tu ID tran ('2401.15884v2', 'arXiv:2401.15884') hoac URL abs/pdf."""
    raw = (raw or "").strip()
    raw = re.sub(r"^arxiv:\s*", "", raw, flags=re.IGNORECASE)
    if ARXIV_ID_RE.match(raw):
        return raw
    m = _ARXIV_URL_RE.match(raw)
    return m.group(1) if m else None


def _headers() -> dict:
    return {"X-API-Key": API_KEY} if API_KEY else {}

# ──────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS — GIAO DIEN PREMIUM DARK MODE
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Root Variables ── */
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-card: #1c2128;
    --bg-input: #21262d;
    --accent: #58a6ff;
    --accent-glow: rgba(88, 166, 255, 0.15);
    --accent-green: #3fb950;
    --accent-orange: #e3b341;
    --accent-red: #f85149;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #6e7681;
    --border: #30363d;
    --border-hover: #484f58;
    --radius: 12px;
    --radius-sm: 8px;
}

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: var(--bg-primary);
    color: var(--text-primary);
}

/* ── Hide default Streamlit elements ── */
/* Chi an menu/nut Deploy/footer - KHONG an header hay stToolbar: tu Streamlit 1.63
   nut mo lai sidebar (stExpandSidebarButton) nam ben trong stHeader > stToolbar,
   an mot trong hai la mat nut, sidebar thu gon roi thi khong mo lai duoc. */
#MainMenu, footer, [data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stDecoration"] { visibility: hidden; }
[data-testid="stExpandSidebarButton"] { visibility: visible !important; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding: 1.5rem 2rem 1rem; max-width: 100%; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] > div { padding: 1.5rem 1rem; }

/* ── Sidebar Logo / Title ── */
.sidebar-title {
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: -0.5px;
    margin-bottom: 0.2rem;
}
.sidebar-subtitle {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-bottom: 1.5rem;
}

/* ── Divider ── */
.sidebar-divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 1rem 0;
}

/* ── Section Label ── */
.section-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    margin-bottom: 0.6rem;
}

/* ── Status Badge ── */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.3px;
}
.badge-green { background: rgba(63, 185, 80, 0.15); color: var(--accent-green); border: 1px solid rgba(63,185,80,0.3); }
.badge-red   { background: rgba(248, 81, 73, 0.15);  color: var(--accent-red);   border: 1px solid rgba(248,81,73,0.3); }
.badge-blue  { background: rgba(88, 166, 255, 0.15); color: var(--accent);       border: 1px solid rgba(88,166,255,0.3); }
.badge-orange{ background: rgba(227,179,65, 0.15);   color: var(--accent-orange);border: 1px solid rgba(227,179,65,0.3); }

/* ── Server Status Pill ── */
.server-online  { color: var(--accent-green); font-size: 0.8rem; font-weight: 500; }
.server-offline { color: var(--accent-red);   font-size: 0.8rem; font-weight: 500; }

/* ── Chat Container ── */
.chat-header {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.5px;
    margin-bottom: 0.25rem;
}
.chat-subheader {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: 1.5rem;
}

/* ── Message Bubbles ── */
.msg-user {
    background: var(--accent-glow);
    border: 1px solid rgba(88,166,255,0.25);
    border-radius: var(--radius) var(--radius) 4px var(--radius);
    padding: 0.9rem 1.1rem;
    margin: 0.5rem 0;
    max-width: 80%;
    margin-left: auto;
    color: var(--text-primary);
    font-size: 0.9rem;
    line-height: 1.6;
}
/* Bong bong cua agent la st.container(key="msg_ai_<i>") -> Streamlit gan class
   st-key-msg_ai_<i>; noi dung render bang st.markdown (co markdown, Streamlit tu
   chan HTML) thay vi nhung chuoi da escape vao <div> (mat het **dam**, danh sach). */
.msg-ai, [class*="st-key-msg_ai_"] {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius) var(--radius) var(--radius) 4px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
    max-width: 88%;
    color: var(--text-primary);
    font-size: 0.9rem;
    line-height: 1.7;
}
[class*="st-key-msg_ai_"] { gap: 0.25rem; }
[class*="st-key-msg_ai_"] p, [class*="st-key-msg_ai_"] li { font-size: 0.9rem; line-height: 1.7; }
.msg-meta {
    font-size: 0.72rem;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── Source Citation Card ── */
.source-card {
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius-sm);
    padding: 0.65rem 0.9rem;
    margin-bottom: 0.5rem;
    font-size: 0.8rem;
}
.source-section {
    color: var(--accent);
    font-weight: 600;
    font-size: 0.78rem;
    margin-bottom: 0.3rem;
}
.source-preview {
    color: var(--text-secondary);
    line-height: 1.5;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
}

/* ── Paper Info Card ── */
.paper-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.7rem 0.9rem;
    font-size: 0.82rem;
    color: var(--text-secondary);
}
.paper-title {
    color: var(--text-primary);
    font-weight: 600;
    font-size: 0.85rem;
    margin-bottom: 0.3rem;
}

/* ── Streamlit Widget Overrides ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background: var(--bg-input) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', sans-serif !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-glow) !important;
}

.stButton > button {
    background: var(--accent) !important;
    color: #0d1117 !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: #79c0ff !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 15px var(--accent-glow) !important;
}

.stSelectbox > div > div {
    background: var(--bg-input) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
}

/* ── Welcome Screen ── */
.welcome-box {
    background: var(--bg-card);
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    padding: 3rem 2rem;
    text-align: center;
    color: var(--text-muted);
}
.welcome-icon { font-size: 3rem; margin-bottom: 0.8rem; }
.welcome-text { font-size: 0.9rem; line-height: 1.6; }

/* ── Spinner tweak ── */
.stSpinner > div { border-top-color: var(--accent) !important; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# SESSION STATE — Khoi tao cac bien trang thai khi app lan dau chay
# ──────────────────────────────────────────────────────────────────────────────

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []   # List[dict]: toan bo lich su chat
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None    # Thread ID cua phien hoi thoai hien tai
if "selected_paper" not in st.session_state:
    st.session_state.selected_paper = None  # paper_id dang duoc chon


# ──────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS — Giao tiep voi FastAPI Backend
# ──────────────────────────────────────────────────────────────────────────────

def _error_from_response(r: requests.Response) -> dict:
    """Doi response loi cua server thanh {'error': msg}; hien `detail` neu co."""
    if r.status_code == 401:
        return {"error": MSG_UNAUTHORIZED}
    try:
        detail = r.json().get("detail")
    except Exception:
        detail = None
    if detail is None:
        detail = f"HTTP {r.status_code}: {r.text[:300]}"
    elif not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)  # 422: detail la list
    return {"error": detail}


def check_server() -> bool:
    """Kiem tra FastAPI server co dang chay khong."""
    try:
        # Tăng timeout lên 10s cho kết nối mạng HTTPS xuyên quốc gia
        r = requests.get(f"{API_BASE}/health", headers=_headers(), timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def get_papers() -> tuple[list[dict], str | None]:
    """Lay danh sach bai bao da duoc index. Tra ve (papers, loi_neu_co)."""
    try:
        r = requests.get(f"{API_BASE}/papers", headers=_headers(), timeout=10)
        if r.status_code == 200:
            return r.json().get("papers", []), None
        return [], _error_from_response(r)["error"]
    except Exception as e:
        return [], str(e)


def upload_pdf(file_bytes: bytes, filename: str, paper_id: str | None = None) -> dict | None:
    """
    Upload file PDF len FastAPI server. Server tra ve 202 NGAY (khong doi
    parse/embed/index xong) - viec do chay nen, xem app/api/routes.py.
    Goi poll_paper_status() sau ham nay de biet khi nao thuc su xong.

    Ngoai le: 200 (khong phai 202) khi noi dung file (sha256) da duoc index
    truoc do - body co status='ready' va paper_id la cua paper CU (co the
    khac paper_id vua nhap), khong can poll.
    """
    try:
        files = {"file": (filename, file_bytes, "application/pdf")}
        data = {"paper_id": paper_id} if paper_id else {}
        r = requests.post(
            f"{API_BASE}/upload", files=files, data=data, headers=_headers(), timeout=30
        )
        if r.status_code in (200, 202):
            return r.json()
        return _error_from_response(r)
    except Exception as e:
        return {"error": str(e)}


def import_arxiv(arxiv_id: str) -> dict | None:
    """
    POST /papers/arxiv. Cung ngu nghia voi upload_pdf: 202 = paper moi (poll
    status), 200 = da index truoc do (status='ready', khong can poll).
    """
    try:
        r = requests.post(
            f"{API_BASE}/papers/arxiv",
            json={"arxiv_id": arxiv_id},
            headers=_headers(),
            timeout=60,  # server con phai tai PDF tu arxiv.org
        )
        if r.status_code in (200, 202):
            return r.json()
        return _error_from_response(r)
    except Exception as e:
        return {"error": str(e)}


def poll_paper_status(paper_id: str, timeout_sec: int = 600, interval_sec: float = 2.0) -> dict:
    """
    Poll GET /papers/{paper_id}/status cho den khi status != 'processing'.
    timeout_sec mac dinh 10 phut - du du cho paper nhieu chunk phai cho
    nhieu vong cooldown 61s cua Gemini free tier (xem embeddings.py).
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = requests.get(
                f"{API_BASE}/papers/{paper_id}/status", headers=_headers(), timeout=10
            )
            if r.status_code == 200:
                info = r.json()
                if info["status"] != "processing":
                    return info
            elif r.status_code in (401, 404):
                # Loi vinh vien - khong poll tiep den het timeout.
                return {"status": "failed", "error": _error_from_response(r)["error"]}
        except Exception:
            pass
        time.sleep(interval_sec)
    return {"status": "failed", "error": "Timeout khi cho index - kiem tra log server."}


def ask_question(question: str, paper_id: str, thread_id: str | None) -> dict | None:
    """Gui cau hoi toi Agent va nhan cau tra loi."""
    try:
        payload = {
            "question": question,
            "paper_id": paper_id,
            "thread_id": thread_id,
        }
        r = requests.post(f"{API_BASE}/ask", json=payload, headers=_headers(), timeout=120)
        if r.status_code == 200:
            return r.json()
        return _error_from_response(r)
    except Exception as e:
        return {"error": str(e)}


def select_paper(paper_id: str) -> None:
    """Chon paper va mo phien chat moi (neu khac paper dang chon)."""
    if paper_id != st.session_state.selected_paper:
        st.session_state.selected_paper = paper_id
        st.session_state.chat_history = []
        st.session_state.thread_id = f"session_{uuid.uuid4().hex[:8]}"


def handle_index_result(result: dict | None) -> None:
    """
    Xu ly ket qua /upload hoac /papers/arxiv (cung ngu nghia):
    loi -> st.error; 200/ready (dedup) -> chon paper cu; 202 -> poll roi chon paper moi.
    """
    if not result:
        return
    if "error" in result:
        st.error(f"❌ {result['error']}")
        return
    if result.get("status") == "ready":
        # 200 (dedup): da index truoc do, server tra ve paper CU (paper_id co
        # the khac cai vua nhap) - khong can poll.
        reused_id = result["paper_id"]
        select_paper(reused_id)
        # Lưu thông báo qua session_state vì st.rerun() xoá mọi st.info vẽ trước đó
        st.session_state.upload_notice = (
            f"ℹ️ Bài báo này đã được index trước đó — dùng lại paper_id `{reused_id}` "
            f"({result.get('num_chunks', 0)} chunks)."
        )
        st.rerun()
        return
    # 202: parse/embed/index chay nen o server. Poll status de biet khi nao xong.
    with st.spinner("Đang parse + embed + index (có thể mất vài phút nếu paper nhiều chunk)..."):
        final = poll_paper_status(result["paper_id"])
    if final.get("status") == "ready":
        select_paper(result["paper_id"])
        st.session_state.upload_notice = (
            f"✅ Index thành công! {final['num_chunks']} chunks đã sẵn sàng."
        )
        st.rerun()
    else:
        st.error(f"❌ Index thất bại: {final.get('error', 'không rõ nguyên nhân, xem log server.')}")


# ──────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    # ── Logo ──
    st.markdown('<div class="sidebar-title">🧠 ArXiv RAG Agent</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-subtitle">Agentic Retrieval-Augmented Generation</div>', unsafe_allow_html=True)

    # ── Server Status ──
    server_ok = check_server()
    if server_ok:
        st.markdown('🟢 <span class="server-online">Server đang hoạt động</span>', unsafe_allow_html=True)
    else:
        st.markdown('🔴 <span class="server-offline">Server chưa chạy</span>', unsafe_allow_html=True)
        if API_BASE.startswith("http://127.0.0.1") or API_BASE.startswith("http://localhost"):
            # Tren Streamlit Cloud ma roi vao nhanh nay = chua dat API_BASE trong Secrets.
            st.warning(
                "Chưa cấu hình `API_BASE` nên UI đang gọi API ở máy local.\n\n"
                "- Trên Streamlit Cloud: vào **Settings → Secrets**, thêm `API_BASE` và `APP_API_KEY`.\n"
                "- Chạy local: `python -m uvicorn app.api.main:app --port 8000`"
            )
        else:
            st.warning(f"Không kết nối được tới API: `{API_BASE}`. Kiểm tra `API_BASE` và trạng thái server.")

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # ── Upload PDF ──
    st.markdown('<div class="section-label">📄 Upload bài báo mới</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        label="Chọn file PDF",
        type=["pdf"],
        label_visibility="collapsed",
    )

    custom_id = st.text_input(
        label="Paper ID tùy chỉnh (tùy chọn)",
        placeholder="vd: cortexode_2023",
        label_visibility="visible",
    )

    # Kiem tra truoc o phia client (server cung kiem tra lai, day chi de bao loi than thien)
    upload_problem = None
    if uploaded_file is not None and uploaded_file.size > MAX_UPLOAD_BYTES:
        upload_problem = (
            f"File quá lớn ({uploaded_file.size / 1024 / 1024:.1f} MB). "
            f"Giới hạn tối đa là {MAX_UPLOAD_BYTES // 1024 // 1024} MB."
        )
    elif custom_id.strip() and not PAPER_ID_RE.match(custom_id.strip()):
        upload_problem = (
            "Paper ID không hợp lệ: chỉ dùng chữ thường a-z, số, `_` hoặc `-`, "
            "bắt đầu bằng chữ/số, tối đa 64 ký tự (vd: `cortexode_2023`)."
        )
    if upload_problem:
        st.warning(upload_problem)

    if st.button(
        "⬆️  Upload & Index",
        disabled=not (server_ok and uploaded_file and not upload_problem),
        use_container_width=True,
    ):
        with st.spinner("Đang gửi PDF lên server..."):
            result = upload_pdf(
                file_bytes=uploaded_file.read(),
                filename=uploaded_file.name,
                paper_id=custom_id.strip() or None,
            )
        handle_index_result(result)

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # ── Nhap tu arXiv ──
    st.markdown('<div class="section-label">🔗 Nhập từ arXiv</div>', unsafe_allow_html=True)
    arxiv_input = st.text_input(
        label="arXiv ID hoặc URL",
        placeholder="vd: 2401.15884 hoặc https://arxiv.org/abs/2401.15884",
        key="arxiv_input",
    )
    arxiv_id = extract_arxiv_id(arxiv_input) if arxiv_input.strip() else None
    if arxiv_input.strip() and not arxiv_id:
        st.warning(
            "Không nhận ra arXiv ID. Nhập dạng `2401.15884` (có thể kèm `v2`) "
            "hoặc URL `arxiv.org/abs/...` / `arxiv.org/pdf/...`."
        )

    upload_notice = st.session_state.pop("upload_notice", None)
    if upload_notice:
        st.info(upload_notice)

    if st.button("📥  Nhập & Index từ arXiv", disabled=not (server_ok and arxiv_id), use_container_width=True):
        with st.spinner("Đang tải PDF từ arXiv..."):
            result = import_arxiv(arxiv_id)
        handle_index_result(result)

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # ── Chon bai bao ──
    st.markdown('<div class="section-label">🗂️ Chọn bài báo</div>', unsafe_allow_html=True)

    papers, papers_error = get_papers() if server_ok else ([], None)
    if papers_error:
        st.error(f"❌ Không tải được danh sách bài báo: {papers_error}")

    if papers:
        paper_options = {p["paper_id"]: f"{p['title']} ({p['num_chunks']} chunks)" for p in papers}
        paper_ids = list(paper_options.keys())
        chosen = st.selectbox(
            label="Bài báo",
            options=paper_ids,
            # Giữ đúng paper đang chọn (vd paper_id cũ vừa được dùng lại sau
            # upload trùng file) thay vì luôn nhảy về phần tử đầu tiên.
            index=(paper_ids.index(st.session_state.selected_paper)
                   if st.session_state.selected_paper in paper_ids else 0),
            format_func=lambda pid: paper_options[pid],
            label_visibility="collapsed",
        )

        if chosen != st.session_state.selected_paper:
            select_paper(chosen)   # Xoa lich su + thread_id moi khi doi bai bao
            st.rerun()

        # Hien thi paper info
        selected_info = next((p for p in papers if p["paper_id"] == chosen), None)
        if selected_info:
            # XSS: title lay tu ten file nguoi upload -> phai escape
            st.markdown(f"""
            <div class="paper-card">
                <div class="paper-title">{esc(selected_info['title'])}</div>
                ID: <code>{esc(selected_info['paper_id'])}</code><br>
                Chunks: {esc(selected_info['num_chunks'])}
            </div>""", unsafe_allow_html=True)
    elif not papers_error:
        st.caption("Chưa có bài báo nào. Hãy upload PDF hoặc nhập từ arXiv ở trên.")

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # ── Session Info ──
    st.markdown('<div class="section-label">💬 Phiên chat</div>', unsafe_allow_html=True)

    if st.session_state.thread_id:
        st.caption(f"Thread: `{st.session_state.thread_id}`")
        st.caption(f"Tin nhắn: {len(st.session_state.chat_history)}")
    else:
        st.caption("Chưa có phiên chat nào.")

    if st.button("🗑️  Xóa lịch sử chat", use_container_width=True, type="secondary"):
        st.session_state.chat_history = []
        st.session_state.thread_id = f"session_{uuid.uuid4().hex[:8]}"
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# MAIN AREA — CHAT INTERFACE
# ──────────────────────────────────────────────────────────────────────────────

st.markdown('<div class="chat-header">🧠 Hỏi đáp về bài báo khoa học</div>', unsafe_allow_html=True)

paper_name = (
    st.session_state.selected_paper
    if st.session_state.selected_paper
    else "chưa có bài báo nào được chọn"
)
st.markdown(
    f'<div class="chat-subheader">Đang làm việc với: <strong>{esc(paper_name)}</strong></div>',
    unsafe_allow_html=True,
)

# ── Lich su chat ──
if not st.session_state.chat_history:
    st.markdown("""
    <div class="welcome-box">
        <div class="welcome-icon">📚</div>
        <div class="welcome-text">
            Chưa có cuộc trò chuyện nào.<br>
            Hãy <strong>chọn một bài báo</strong> ở thanh bên trái,<br>
            sau đó <strong>nhập câu hỏi</strong> bên dưới để bắt đầu.
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    for msg_idx, msg in enumerate(st.session_state.chat_history):
        if msg["role"] == "user":
            st.markdown(f"""
            <div class="msg-user">
                <div class="msg-meta">🧑‍💻 Bạn &nbsp;·&nbsp; {esc(msg['time'])}</div>
                {esc_multiline(msg['content'])}
            </div>""", unsafe_allow_html=True)

        else:
            # Agent response
            grade_badge = (
                '<span class="badge badge-green">✔ Tài liệu đủ (grade: yes)</span>'
                if msg.get("grade") == "yes"
                else '<span class="badge badge-orange">⚠ Tài liệu thiếu (grade: no)</span>'
            )
            rewrite_badge = ""
            if msg.get("rewrite_count", 0) > 0:
                rewrite_badge = f'<span class="badge badge-blue">↺ Viết lại x{esc(msg["rewrite_count"])}</span>'

            with st.container(key=f"msg_ai_{msg_idx}"):
                st.markdown(f"""
                <div class="msg-meta">
                    🤖 Agent &nbsp;·&nbsp; {esc(msg['time'])}
                    &nbsp; {grade_badge} &nbsp; {rewrite_badge}
                </div>""", unsafe_allow_html=True)
                # XSS: KHONG unsafe_allow_html - Streamlit hien HTML tho trong cau tra
                # loi duoi dang chu, chi render markdown (dam, danh sach, code, cong thuc).
                st.markdown(msg["content"])

            # ── Nguon trich dan ──
            sources = msg.get("sources", [])
            if sources:
                with st.expander(f"📎 Nguồn trích dẫn ({len(sources)} đoạn văn)"):
                    for i, src in enumerate(sources, 1):
                        # section/content_preview den tu PDF -> khong tin cay, phai escape
                        page_num = src.get("page_num")
                        page_html = f" · trang {esc(page_num)}" if page_num is not None else ""
                        st.markdown(f"""
                        <div class="source-card">
                            <div class="source-section">#{i} · {esc(src['section'])}{page_html}</div>
                            <div class="source-preview">{esc_multiline(src['content_preview'])}…</div>
                            <div style="margin-top:4px; font-size:0.7rem; color:var(--text-muted);">
                                ID: <code>{esc(src['chunk_id'])}</code>
                            </div>
                        </div>""", unsafe_allow_html=True)


# ── Input box ──
st.markdown("<br>", unsafe_allow_html=True)

can_ask = server_ok and st.session_state.selected_paper is not None

with st.form(key="chat_form", clear_on_submit=True):
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        user_input = st.text_area(
            label="Câu hỏi",
            placeholder=(
                "Nhập câu hỏi về bài báo... (vd: What are the main contributions?)"
                if can_ask
                else "Hãy chọn một bài báo ở thanh bên trái trước."
            ),
            height=80,
            max_chars=1000,   # khop AskRequest.max_length phia server
            disabled=not can_ask,
            label_visibility="collapsed",
        )
    with col_btn:
        submit = st.form_submit_button(
            "Gửi →",
            disabled=not can_ask,
            use_container_width=True,
        )

# ── Xu ly khi nhan Gui ──
if submit and user_input.strip() and can_ask:
    question = user_input.strip()
    now = datetime.now().strftime("%H:%M")

    # Them tin nhan nguoi dung vao lich su
    st.session_state.chat_history.append({
        "role": "user",
        "content": question,
        "time": now,
    })

    # Khoi tao thread_id neu chua co
    if not st.session_state.thread_id:
        st.session_state.thread_id = f"session_{uuid.uuid4().hex[:8]}"

    # Goi Agent qua FastAPI
    with st.spinner("🤖 Agent đang tìm kiếm và phân tích..."):
        result = ask_question(
            question=question,
            paper_id=st.session_state.selected_paper,
            thread_id=st.session_state.thread_id,
        )

    if result and "error" not in result:
        # Cap nhat thread_id tu server (trong truong hop server tu tao)
        st.session_state.thread_id = result.get("thread_id", st.session_state.thread_id)

        # Them phan hoi cua Agent vao lich su
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": result["answer"],
            "time": datetime.now().strftime("%H:%M"),
            "grade": result.get("grade", "yes"),
            "rewrite_count": result.get("rewrite_count", 0),
            "sources": result.get("sources", []),
        })
    else:
        error_msg = result.get("error") if result else "Không thể kết nối tới server."
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": f"❌ Lỗi: {error_msg}",
            "time": datetime.now().strftime("%H:%M"),
            "grade": "no",
            "rewrite_count": 0,
            "sources": [],
        })

    st.rerun()
