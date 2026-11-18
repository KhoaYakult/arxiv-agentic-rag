"""
app/llm/prompt_templates.py
=============================
Tap hop cac Prompt Template cho toan bo he thong RAG Agent.

Prompt Template la gi?
  - La "to huong dan" gui kem cau hoi cho LLM.
  - Giong nhu khi ban giao viec cho nhan vien: ban khong chi noi
    "tra loi cau hoi nay" ma con phai noi ro "ban la ai, lam gi,
    dua vao tai lieu nao, khong duoc lam gi".

Tai sao can nhieu template khac nhau?
  - Moi buoc trong pipeline co nhiem vu khac nhau:
    1. RAG_ANSWER : Tong hop cau tra loi tu context (nhiem vu chinh)
    2. GRADE_DOCS : Cham diem context co du tot khong (kiem tra chat luong)
    3. REWRITE_QUERY : Viet lai cau hoi khi retrieve that bai (sua sai)

Cach su dung voi LangChain:
    from langchain_core.prompts import ChatPromptTemplate
    prompt = ChatPromptTemplate.from_template(RAG_ANSWER_TEMPLATE)
    chain = prompt | llm   # Noi prompt voi LLM thanh 1 chuoi xu ly
    result = chain.invoke({"context": "...", "question": "..."})
"""

# ──────────────────────────────────────────────────────────────────────────────
# 1. RAG ANSWER TEMPLATE
# Nhiem vu: Tong hop cau tra loi tu context da duoc retrieve
# ──────────────────────────────────────────────────────────────────────────────

RAG_ANSWER_TEMPLATE = """You are a professional research assistant specialized in analyzing scientific papers.
Your task is to answer the user's question based ONLY on the provided context from the paper.

Rules:
- Answer based ONLY on the context below. Do NOT use your own knowledge.
- Each context passage starts with a number in square brackets, like [1].
- Citations are MANDATORY: end every sentence or bullet that uses the context with the passage number(s) in square brackets, e.g. "The model reaches 38.1 BLEU [2]." or "Both methods share this step [1, 3]." An answer that uses the context but has no [n] marker is wrong.
- Cite EACH sentence separately, not once per paragraph. If several sentences in a row come from the same passage, repeat the marker on every one of them, e.g. "The method first retrieves documents [2]. It then reranks them [2]." Only a sentence that states nothing from the paper (for example "The paper does not report this.") may have no marker. Only use numbers that appear in the context. Never invent a number, and do not add a separate reference list at the end. Use plain square brackets only: write [1], never 【1】 or 【1†L4-L5】.
- If the context does not contain enough information, clearly state that the provided paper sections do not contain enough information, and do not cite anything for that claim.
- Be precise and cite specific details (numbers, method names, table references) when available.
- Structure your answer clearly. Use bullet points for multiple findings.
- Answer in the same language as the question (Vietnamese or English).
{context_note}
===== CONTEXT FROM PAPER =====
{context}

===== CHAT HISTORY =====
{chat_history}

===== QUESTION =====
{question}

===== ANSWER ====="""


# Chen vao {context_note} cua RAG_ANSWER_TEMPLATE khi grader van cham "no" sau khi het luot
# rewrite. Eval 2026-11-16: q49 (cau bay) grader "no" ca 3 lan nhung generate khong biet,
# tra loi bia "28.4 BLEU" lay tu cau hinh khac. Khong chan cung vi q46 grade "no" van tra loi dung.
INSUFFICIENT_CONTEXT_NOTE = """
WARNING: An automatic check judged that the passages below probably do NOT answer this question.
- Answer only if a passage states the answer explicitly AND for exactly what was asked (same model, variant, dataset, split, setting and metric).
- A number or claim about a different model, dataset, split or setting is NOT an answer. Do not present it as one.
- Otherwise say clearly that the provided paper sections do not contain this information. You may briefly mention what the paper does report instead, with its citation.
"""

# ──────────────────────────────────────────────────────────────────────────────
# 2. GRADE DOCUMENTS TEMPLATE (Corrective RAG)
# Nhiem vu: LLM tu cham diem — context co du de tra loi cau hoi khong?
# ──────────────────────────────────────────────────────────────────────────────

GRADE_DOCS_TEMPLATE = """You are a grader assessing whether a set of retrieved document chunks
is relevant enough to answer a user's question about a scientific paper.

Task: Look at the retrieved context and the question, then decide:
- "yes" : The context contains enough information to answer the question.
- "no"  : The context does NOT contain relevant information for this question.

Be strict: if the context only vaguely mentions the topic but lacks specific details
needed to answer the question properly, grade "no".

===== RETRIEVED CONTEXT =====
{context}

===== QUESTION =====
{question}

Grade (answer with ONLY "yes" or "no"):"""

# ──────────────────────────────────────────────────────────────────────────────
# 3. REWRITE QUERY TEMPLATE
# Nhiem vu: Viet lai cau hoi ro rang hon khi retrieve that bai
# ──────────────────────────────────────────────────────────────────────────────

REWRITE_QUERY_TEMPLATE = """You are a query rewriter for a scientific paper search system.
The original question did not retrieve good results from the paper database.

Your task: Rewrite the question to be more specific, using academic/technical terms
that are likely to appear in the paper text.

Guidelines:
- Keep abbreviations and acronyms exactly as written (e.g. "CRAG", "DPR", "BLEU"); do NOT expand them or guess what they stand for
- Do NOT add facts, numbers, names or details that are not in the original question
- You may add general technical terms that the paper likely uses
- Keep the same intent and roughly the same length as the original question
- Return ONLY the rewritten question, nothing else

Original question: {question}

Rewritten question:"""


# ──────────────────────────────────────────────────────────────────────────────
# 4. TRANSLATE QUERY TEMPLATE
# Nhiem vu: dich cau hoi tieng Viet sang tieng Anh, CHI dung cho nhanh tim tu khoa
# (bai bao tieng Anh). Dense, rerank va cau tra loi van theo cau hoi goc.
# ──────────────────────────────────────────────────────────────────────────────

TRANSLATE_QUERY_TEMPLATE = """Translate this question about a scientific paper into English, for keyword search over the English paper. Keep technical terms, model names, dataset names and numbers exactly. Output only the English question.

Question: {question}"""

# ──────────────────────────────────────────────────────────────────────────────
# 5. CONDENSE QUERY TEMPLATE
# Nhiem vu: cau hoi noi tiep ("no train tren dataset nao?") -> cau TU DU NGHIA de TIM.
# Chi chay khi co lich su chat. Gop luon viec dich sang tieng Anh (thay TRANSLATE_QUERY khi
# co lich su) -> 1 luot goi. Cau tra loi van theo cau goc + lich su.
# ──────────────────────────────────────────────────────────────────────────────

CONDENSE_QUERY_TEMPLATE = """Rewrite the user's LAST question so it can be understood without the conversation, for searching inside one scientific paper.
- Replace pronouns and vague references ("it", "this method", "the first one", "nó", "cái đó", "còn ... thì sao") with what they refer to in the conversation.
- Keep technical terms, model names, dataset names and numbers exactly as written.
- Do not add facts or numbers taken from the assistant's answers; only resolve what the question refers to.
- If the question is already self-contained, keep it unchanged.

Return ONLY JSON: {{"question": "<standalone question, in the same language as the last question>", "english": "<the same standalone question in English>"}}

Conversation:
{chat_history}

Last question: {question}"""

# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT: Xem thu cac template
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path

    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    print("=" * 60, flush=True)
    print("[TEST] Buoc 4.2 — Kiem tra Prompt Templates", flush=True)
    print("=" * 60, flush=True)

    # ── Test 1: Hien thi cac bien trong template ──
    # LangChain dung cu phap {variable_name} de danh dau bien.
    # Khi goi chain.invoke({"context": "...", "question": "..."}),
    # LangChain se tu dong thay the cac bien nay.
    from langchain_core.prompts import ChatPromptTemplate

    templates = {
        "RAG_ANSWER": RAG_ANSWER_TEMPLATE,
        "GRADE_DOCS": GRADE_DOCS_TEMPLATE,
        "REWRITE_QUERY": REWRITE_QUERY_TEMPLATE,
        "TRANSLATE_QUERY": TRANSLATE_QUERY_TEMPLATE,
    }

    for name, template in templates.items():
        prompt = ChatPromptTemplate.from_template(template)
        # input_variables: danh sach cac bien can truyen vao khi goi invoke()
        print(f"\n[{name}]", flush=True)
        print(f"  Cac bien can truyen: {prompt.input_variables}", flush=True)
        print(f"  Do dai template    : {len(template)} ky tu", flush=True)

    # ── Test 2: Thu tao prompt hoan chinh voi du lieu mau ──
    print("\n" + "-" * 60, flush=True)
    print("[TEST 2] Tao prompt RAG_ANSWER voi du lieu mau:", flush=True)

    rag_prompt = ChatPromptTemplate.from_template(RAG_ANSWER_TEMPLATE)

    # format_messages() thay the cac bien thanh gia tri thuc te
    messages = rag_prompt.format_messages(
        context="CortexODE achieves a Dice coefficient of 0.939...",
        chat_history="",
        question="What is the Dice coefficient?",
    )

    print(f"  Prompt hoan chinh ({len(messages[0].content)} ky tu):", flush=True)
    # Chi in 300 ky tu dau tien de khong tran terminal
    print(f"  {messages[0].content[:300]}...", flush=True)

    # ── Test 3: Thu ket noi voi LLM thuc te ──
    print("\n" + "-" * 60, flush=True)
    print("[TEST 3] Ket noi template voi LLM thuc te...", flush=True)

    from app.llm.llm_factory import get_llm

    llm = get_llm()

    # Toan tu "|" (pipe) trong LangChain tao ra 1 "chain" (chuoi xu ly):
    #   prompt | llm
    chain = rag_prompt | llm

    # invoke() voi cac bien → prompt duoc format → gui len LLM → nhan cau tra loi
    result = chain.invoke({
        "context": "CortexODE achieves a Dice coefficient of 0.939 on white matter segmentation.",
        "chat_history": "",
        "question": "What is the Dice coefficient of CortexODE?",
    })

    print(f"  Tra loi: {result.content}", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("[SUCCESS] Buoc 4.2 hoan tat! Prompt Templates hoat dong tot.", flush=True)
    print("=" * 60, flush=True)
