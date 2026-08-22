"""
streamlit_app.py
=================
Giao dien nguoi dung cho ArXiv Agentic RAG.
Giao tiep voi FastAPI Backend qua HTTP REST API.

Cach chay:
    # Terminal 1: Bat FastAPI server
    python -m uvicorn app.api.main:app --port 8000 --reload

    # Terminal 2: Bat Streamlit UI
    streamlit run streamlit_app.py
"""

import os
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

# Tự động lấy URL Railway công khai khi deploy
RAILWAY_URL = "https://arxiv-agentic-rag-production.up.railway.app"

API_BASE = os.environ.get(
    "API_BASE",
    st.secrets.get("API_BASE", RAILWAY_URL)
).rstrip("/")
if not API_BASE.endswith("/api/v1"):
    API_BASE = f"{API_BASE}/api/v1"

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
#MainMenu, footer, header { visibility: hidden; }
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
.msg-ai {
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

def check_server() -> bool:
    """Kiem tra FastAPI server co dang chay khong."""
    try:
        r = requests.get(f"{API_BASE}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def get_papers() -> list[dict]:
    """Lay danh sach bai bao da duoc index tu server."""
    try:
        r = requests.get(f"{API_BASE}/papers", timeout=5)
        if r.status_code == 200:
            return r.json().get("papers", [])
    except Exception:
        pass
    return []


def upload_pdf(file_bytes: bytes, filename: str, paper_id: str | None = None) -> dict | None:
    """Upload file PDF len FastAPI server."""
    try:
        files = {"file": (filename, file_bytes, "application/pdf")}
        data = {"paper_id": paper_id} if paper_id else {}
        # Tăng timeout lên 300s (5 phút) cho các file PDF nặng (14MB+)
        r = requests.post(f"{API_BASE}/upload", files=files, data=data, timeout=300)
        if r.status_code == 201:
            return r.json()
        else:
            return {"error": r.json().get("detail", "Loi khong xac dinh")}
    except Exception as e:
        return {"error": str(e)}


def ask_question(question: str, paper_id: str, thread_id: str | None) -> dict | None:
    """Gui cau hoi toi Agent va nhan cau tra loi."""
    try:
        payload = {
            "question": question,
            "paper_id": paper_id,
            "thread_id": thread_id,
        }
        r = requests.post(f"{API_BASE}/ask", json=payload, timeout=120)
        if r.status_code == 200:
            return r.json()
        else:
            return {"error": r.json().get("detail", "Loi khong xac dinh")}
    except Exception as e:
        return {"error": str(e)}


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
        st.warning("Hãy chạy lệnh sau trước:\n```\npython -m uvicorn app.api.main:app --port 8000\n```")

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

    if st.button("⬆️  Upload & Index", disabled=not (server_ok and uploaded_file), use_container_width=True):
        with st.spinner("Đang xử lý PDF... có thể mất 30-60 giây"):
            result = upload_pdf(
                file_bytes=uploaded_file.read(),
                filename=uploaded_file.name,
                paper_id=custom_id.strip() or None,
            )
        if result and "error" not in result:
            st.success(f"✅ {result['message']}")
            st.caption(f"Paper ID: `{result['paper_id']}` — {result['num_chunks']} chunks")
            st.rerun()
        elif result:
            st.error(f"❌ {result.get('error')}")

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # ── Chon bai bao ──
    st.markdown('<div class="section-label">🗂️ Chọn bài báo</div>', unsafe_allow_html=True)

    papers = get_papers() if server_ok else []

    if papers:
        paper_options = {p["paper_id"]: f"{p['title']} ({p['num_chunks']} chunks)" for p in papers}
        chosen = st.selectbox(
            label="Bài báo",
            options=list(paper_options.keys()),
            format_func=lambda pid: paper_options[pid],
            label_visibility="collapsed",
        )

        if chosen != st.session_state.selected_paper:
            st.session_state.selected_paper = chosen
            st.session_state.chat_history = []   # Xoa lich su khi doi bai bao
            st.session_state.thread_id = f"session_{uuid.uuid4().hex[:8]}"
            st.rerun()

        # Hien thi paper info
        selected_info = next((p for p in papers if p["paper_id"] == chosen), None)
        if selected_info:
            st.markdown(f"""
            <div class="paper-card">
                <div class="paper-title">{selected_info['title']}</div>
                ID: <code>{selected_info['paper_id']}</code><br>
                Chunks: {selected_info['num_chunks']}
            </div>""", unsafe_allow_html=True)
    else:
        st.caption("Chưa có bài báo nào. Hãy upload PDF ở trên.")

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
    f'<div class="chat-subheader">Đang làm việc với: <strong>{paper_name}</strong></div>',
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
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f"""
            <div class="msg-user">
                <div class="msg-meta">🧑‍💻 Bạn &nbsp;·&nbsp; {msg['time']}</div>
                {msg['content']}
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
                rewrite_badge = f'<span class="badge badge-blue">↺ Viết lại x{msg["rewrite_count"]}</span>'

            st.markdown(f"""
            <div class="msg-ai">
                <div class="msg-meta">
                    🤖 Agent &nbsp;·&nbsp; {msg['time']}
                    &nbsp; {grade_badge} &nbsp; {rewrite_badge}
                </div>
                {msg['content']}
            </div>""", unsafe_allow_html=True)

            # ── Nguon trich dan ──
            sources = msg.get("sources", [])
            if sources:
                with st.expander(f"📎 Nguồn trích dẫn ({len(sources)} đoạn văn)"):
                    for i, src in enumerate(sources, 1):
                        st.markdown(f"""
                        <div class="source-card">
                            <div class="source-section">#{i} · {src['section']}</div>
                            <div class="source-preview">{src['content_preview']}…</div>
                            <div style="margin-top:4px; font-size:0.7rem; color:var(--text-muted);">
                                ID: <code>{src['chunk_id']}</code>
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
            "content": f"❌ **Lỗi:** {error_msg}",
            "time": datetime.now().strftime("%H:%M"),
            "grade": "no",
            "rewrite_count": 0,
            "sources": [],
        })

    st.rerun()
