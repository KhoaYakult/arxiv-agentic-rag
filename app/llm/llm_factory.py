"""
app/llm/llm_factory.py
========================
Factory Pattern: Khoi tao LLM tu bat ky provider nao chi bang 1 dong.

Thiet ke linh hoat:
  - Doi model    → Sua .env, KHONG sua code.
  - Them provider → Them 1 elif, cac module khac KHONG thay doi gi.

Providers duoc ho tro:
  - "groq"   : Groq Cloud (mien phi, nhanh, khong ton RAM)
  - "gemini" : Google Gemini API
  - "ollama" : Ollama Local (chay offline tren may)

Cach su dung:
    from app.llm.llm_factory import get_llm
    llm = get_llm()              # Tu dong chon theo .env
    response = llm.invoke("...") # Giao dien giong nhau bat ke provider
"""

import sys
from pathlib import Path

# Tu dong them thu muc goc du an vao sys.path khi chay file truc tiep
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings


# ──────────────────────────────────────────────────────────────────────────────
# AUTO MODEL PICKER — Tự động chọn model Groq đang hoạt động
# ──────────────────────────────────────────────────────────────────────────────

# Danh sách model ưu tiên (mạnh nhất trước).
# Hàm sẽ lấy danh sách model THỰC SỰ đang active từ Groq API,
# rồi chọn model đầu tiên trong danh sách ưu tiên này mà Groq còn hỗ trợ.
# → Không bao giờ bị lỗi "model decommissioned" nữa!
_GROQ_PREFERRED_MODELS = [
    # Nhóm GPT-OSS (thế hệ mới nhất của Groq, 2026)
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    # Nhóm Meta Llama 4
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    # Nhóm Meta Llama 3.x (cũ hơn nhưng vẫn mạnh)
    "llama-3.3-70b-specdec",
    "llama-3.1-70b-versatile",
    "llama3-70b-8192",
    # Fallback nhẹ hơn
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "gemma2-9b-it",
]


def _pick_best_groq_model(api_key: str) -> str:
    """
    Hỏi Groq API để lấy danh sách model đang THỰC SỰ hoạt động,
    sau đó trả về model tốt nhất theo thứ tự ưu tiên trong _GROQ_PREFERRED_MODELS.

    Nếu API không trả lời được (mất mạng, key lỗi...), fallback về
    giá trị trong config.py (settings.groq_model_name).
    """
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        available_ids = {m.id for m in client.models.list().data}

        for preferred in _GROQ_PREFERRED_MODELS:
            if preferred in available_ids:
                print(f"[INFO] Tu dong chon Groq model: {preferred}", flush=True)
                return preferred

        # Không tìm thấy model nào trong danh sách ưu tiên → dùng model đầu tiên
        if available_ids:
            chosen = sorted(available_ids)[0]
            print(f"[WARN] Khong co model uu tien nao, dung: {chosen}", flush=True)
            return chosen

    except Exception as e:
        print(f"[WARN] Khong the lay danh sach model Groq: {e}", flush=True)
        print(f"[WARN] Fallback ve model trong config: {settings.groq_model_name}", flush=True)

    return settings.groq_model_name


# ──────────────────────────────────────────────────────────────────────────────
# FACTORY FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def get_llm(
    provider: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 5096,
):
    """
    Factory function: khoi tao LLM tu provider bat ky.

    Args:
        provider:    "groq", "gemini", "ollama", hoac None (tu dong detect tu .env).
        temperature: Muc sang tao (0 = chinh xac nhat, 1 = sang tao nhat).
                     Dat 0 cho RAG vi ta can cau tra loi chinh xac, khong can sang tao.
        max_tokens:  Gioi han do dai cau tra loi (1024 tokens ~ 750 tu tieng Anh).

    Returns:
        BaseChatModel: Instance LLM san sang goi .invoke() hoac dung trong LangGraph.
                       Giao dien (interface) giong nhau bat ke provider nao.

    Auto-detect logic (khi provider=None):
        1. Co GROQ_API_KEY   → dung Groq  (tu dong chon model dang hoat dong)
        2. Co GEMINI_API_KEY → dung Gemini
        3. Khong co API key  → fallback ve Ollama local
    """

    # ── TU DONG DETECT PROVIDER NEU KHONG TRUYEN VAO ──
    if provider is None:
        if settings.groq_api_key:
            provider = "groq"
        elif settings.gemini_api_key:
            provider = "gemini"
        else:
            provider = "ollama"

    provider = provider.lower().strip()

    # ── GROQ CLOUD ──
    if provider == "groq":
        from langchain_groq import ChatGroq

        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY chua duoc cau hinh trong .env! "
                "Truy cap https://console.groq.com/keys de lay key mien phi."
            )

        chosen_model = _pick_best_groq_model(settings.groq_api_key)

        llm = ChatGroq(
            model=chosen_model,
            api_key=settings.groq_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        print(f"[SUCCESS] LLM san sang: Groq/{chosen_model}", flush=True)

    # ── GOOGLE GEMINI ──
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY chua duoc cau hinh trong .env! "
                "Truy cap https://aistudio.google.com/apikey de lay key mien phi."
            )

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=settings.gemini_api_key,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        print("[SUCCESS] LLM san sang: Gemini/gemini-2.0-flash", flush=True)

    # ── OLLAMA LOCAL ──
    elif provider == "ollama":
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            model=settings.ollama_llm_model,
            temperature=temperature,
            num_predict=max_tokens,
        )
        print(f"[SUCCESS] LLM san sang: Ollama/{settings.ollama_llm_model} (local)", flush=True)

    else:
        raise ValueError(
            f"Provider '{provider}' khong duoc ho tro. "
            f"Chon: 'groq', 'gemini', hoac 'ollama'."
        )

    return llm


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT: Test ket noi LLM
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("[TEST] Buoc 4.1 — Kiem tra ket noi LLM (Auto-detect)", flush=True)
    print("=" * 60, flush=True)

    # ── Test 1: Khoi tao LLM (tu dong chon provider tu .env) ──
    print("\n[TEST 1] Khoi tao LLM client...", flush=True)
    llm = get_llm()

    # ── Test 2: Cau hoi don gian ──
    # llm.invoke() la ham chinh de goi LLM trong LangChain.
    # Input : chuoi text (hoac list messages).
    # Output: AIMessage object chua .content (cau tra loi).
    print("\n[TEST 2] Gui cau hoi don gian...", flush=True)
    response = llm.invoke("What is 2 + 2? Answer in one word.")
    print(f"  Cau hoi : What is 2 + 2?", flush=True)
    print(f"  Tra loi : {response.content}", flush=True)

    # ── Test 3: Gia lap RAG (context + cau hoi) ──
    # Day la cach LLM se hoat dong trong pipeline thuc te:
    # ta cung cap context tu bai bao + cau hoi → LLM tong hop cau tra loi.
    print("\n[TEST 3] Gia lap RAG: gui context + cau hoi...", flush=True)

    fake_context = (
        "CortexODE is a deep learning framework for cortical surface reconstruction. "
        "It leverages neural ordinary differential equations (ODEs) to deform an input "
        "surface into a target shape by learning a diffeomorphic flow. The framework "
        "achieves a Dice coefficient of 0.939 on white matter segmentation."
    )

    rag_prompt = f"""You are a research assistant. Answer the question based ONLY on the context below.
If the context does not contain enough information, say "I cannot find this in the paper."

===== CONTEXT =====
{fake_context}

===== QUESTION =====
What is the Dice coefficient of CortexODE for white matter segmentation?

===== ANSWER ====="""

    response = llm.invoke(rag_prompt)
    print(f"  Tra loi: {response.content}", flush=True)

    # ── Test 4: Kiem tra token usage ──
    # response_metadata chua thong tin so token da dung.
    # Quan trong de theo doi rate limit mien phi cua Groq.
    print("\n[TEST 4] Thong tin token usage:", flush=True)
    meta = response.response_metadata
    usage = meta.get("usage", meta.get("token_usage", {}))
    print(f"  Prompt tokens : {usage.get('prompt_tokens', 'N/A')}", flush=True)
    print(f"  Output tokens : {usage.get('completion_tokens', 'N/A')}", flush=True)
    print(f"  Total tokens  : {usage.get('total_tokens', 'N/A')}", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("[SUCCESS] Buoc 4.1 hoan tat! LLM hoat dong tot.", flush=True)
    print("=" * 60, flush=True)
