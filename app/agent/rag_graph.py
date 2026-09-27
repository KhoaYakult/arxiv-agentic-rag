"""
app/agent/rag_graph.py - LangGraph RAG Agent (Backend Standard)
Memory: AsyncPostgresSaver - checkpoint luu trong CUNG Postgres DB voi
papers/chunks (settings.database_url), song sot qua redeploy (khac
AsyncSqliteSaver truoc do, luu tren dia ephemeral cua Railway va mat het
moi lan redeploy).

Phase 2: retrieve_node dung repository.hybrid_search() (Postgres/pgvector +
FTS) thay HybridRetriever (ChromaDB + rank_bm25) cua Phase 1. Toan bo graph
chuyen sang async vi asyncpg (thu vien Postgres) chi ho tro async - dung
asyncio.run() chap va o 1 node duy nhat se lam vo pool connection giua cac
lan goi (moi asyncio.run() tao 1 event loop moi, pool cache lai bi gan voi
loop cu da dong). Xem project-memory/FIXED_BUGS.md.
"""

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Annotated, TypedDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages

from app.config import settings

# =============================================================================
# STATE
# =============================================================================

class AgentState(TypedDict):
    question: str
    paper_id: str
    retrieved_chunks: list
    grade: str
    rewrite_count: int
    answer: str
    messages: Annotated[list, add_messages]


MAX_REWRITES = 2
FIRST_STAGE_K = 20  # so ung vien lay tu hybrid_search truoc khi rerank con 5


# =============================================================================
# NODES
# =============================================================================

async def retrieve_node(state: AgentState) -> dict:
    """Tim Top-5 chunks: repository.hybrid_search() (pgvector + FTS) -> rerank."""
    from app.indexing.embeddings import get_embedding_provider
    from app.indexing.reranker import RerankerManager
    from app.storage import repository

    print(f"\n[NODE] retrieve -- {state['question'][:70]}", flush=True)

    provider = get_embedding_provider()
    query_embedding = provider.embed_query(state["question"])

    candidates = await repository.hybrid_search(
        paper_id=state["paper_id"],
        query_text=state["question"],
        query_embedding=query_embedding,
        top_k=FIRST_STAGE_K,
    )

    reranker = RerankerManager()
    chunks = reranker.rerank(state["question"], candidates, top_k=5)

    print(f"[NODE] retrieve -- Tim duoc {len(chunks)} chunks.", flush=True)
    return {"retrieved_chunks": chunks}


async def grade_node(state: AgentState) -> dict:
    """LLM cham diem context co du de tra loi khong."""
    from langchain_core.prompts import ChatPromptTemplate

    from app.llm.llm_factory import get_llm
    from app.llm.prompt_templates import GRADE_DOCS_TEMPLATE

    print(f"[NODE] grade -- {len(state['retrieved_chunks'])} chunks...", flush=True)
    context = "\n\n---\n\n".join([
        f"[Chunk {i+1}] Section: {c['parent_section_name']}\n{c['text'][:400]}"
        for i, c in enumerate(state["retrieved_chunks"])
    ])
    chain = ChatPromptTemplate.from_template(GRADE_DOCS_TEMPLATE) | get_llm()
    response = await chain.ainvoke({"context": context, "question": state["question"]})
    grade = "yes" if "yes" in response.content.lower().strip() else "no"
    print(f"[NODE] grade -- {grade.upper()} (rewrite={state['rewrite_count']})", flush=True)
    return {"grade": grade}


async def rewrite_node(state: AgentState) -> dict:
    """Viet lai cau hoi ro rang hon."""
    from langchain_core.prompts import ChatPromptTemplate

    from app.llm.llm_factory import get_llm
    from app.llm.prompt_templates import REWRITE_QUERY_TEMPLATE

    print(f"[NODE] rewrite -- lan {state['rewrite_count'] + 1}", flush=True)
    chain = ChatPromptTemplate.from_template(REWRITE_QUERY_TEMPLATE) | get_llm()
    response = await chain.ainvoke({"question": state["question"]})
    new_q = response.content.strip()
    print(f"[NODE] rewrite -- moi: {new_q}", flush=True)
    return {"question": new_q, "rewrite_count": state["rewrite_count"] + 1}


async def generate_node(state: AgentState) -> dict:
    """LLM tong hop cau tra loi. Tu dong lay chat history tu messages."""
    from langchain_core.prompts import ChatPromptTemplate

    from app.llm.llm_factory import get_llm
    from app.llm.prompt_templates import RAG_ANSWER_TEMPLATE

    print("[NODE] generate -- dang tong hop...", flush=True)

    # Format 6 tin nhan gan nhat thanh chuoi cho prompt
    recent = state.get("messages", [])[-6:]
    history = ""
    for msg in recent:
        if isinstance(msg, HumanMessage):
            history += f"User: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            history += f"Assistant: {msg.content}\n"

    context = "\n\n---\n\n".join([
        f"[Section: {c['parent_section_name']}]\n{c['text']}"
        for c in state["retrieved_chunks"]
    ])

    chain = ChatPromptTemplate.from_template(RAG_ANSWER_TEMPLATE) | get_llm()
    response = await chain.ainvoke({
        "context": context,
        "chat_history": history,
        "question": state["question"],
    })

    answer = response.content
    print("[NODE] generate -- hoan tat!", flush=True)

    # add_messages tu dong NOI THEM vao lich su cu
    return {
        "answer": answer,
        "messages": [
            HumanMessage(content=state["question"]),
            AIMessage(content=answer),
        ],
    }


# =============================================================================
# CONDITIONAL EDGE
# =============================================================================

def decide_after_grade(state: AgentState) -> str:
    if state["grade"] == "yes":
        print("[EDGE] --> generate", flush=True)
        return "generate"
    if state["rewrite_count"] < MAX_REWRITES:
        print(f"[EDGE] --> rewrite ({state['rewrite_count']+1}/{MAX_REWRITES})", flush=True)
        return "rewrite"
    print("[EDGE] --> generate (het luot rewrite)", flush=True)
    return "generate"


# =============================================================================
# BUILD GRAPH - lazy async singleton
#
# Compile can checkpointer, ma AsyncPostgresSaver can 1 pool psycopg (async)
# de tao - khong the goi await o module-level (luc import). Nen build 1 lan
# duy nhat, lazy, o lan goi ask() dau tien (KHONG phai luc app khoi dong),
# co asyncio.Lock bao ve de nhieu request dau tien dong thoi khong moi cai
# tu build 1 app/pool rieng (cac pool thua se bi ro ri, khong ai close).
# =============================================================================

_rag_app = None
_rag_app_lock = asyncio.Lock()

_checkpointer_pool = None


async def _get_checkpointer():
    """
    AsyncPostgresSaver - luu chat history vao CUNG Postgres DB voi
    papers/chunks (settings.database_url), thay AsyncSqliteSaver tam thoi
    truoc do (SQLite tren dia ephemeral, mat het moi lan Railway redeploy).

    Dung 1 pool psycopg RIENG, KHONG dung chung asyncpg pool cua
    app/storage/repository.py - AsyncPostgresSaver (thu vien
    langgraph-checkpoint-postgres) chi ho tro driver psycopg, khong ho tro
    asyncpg. 2 driver Postgres khac nhau cung tro toi 1 DATABASE_URL khong
    xung dot - Postgres cho phep nhieu client ket noi doc lap binh thuong.

    AsyncConnectionPool(min_size=1, max_size=1) thay vi 1 AsyncConnection tran:
    van dung dung 1 ket noi (giu tong ngan sach ket noi o muc 6 = 5 asyncpg +
    1 checkpointer), nhung pool tu mo lai ket noi moi neu ket noi cu bi rot
    (pooler restart, mang chap chon, idle timeout) - ket noi tran thi hong
    vinh vien, moi /ask sau do deu loi cho toi khi restart ca process.
    check=check_connection: kiem tra ket noi con song truoc khi giao ra.

    prepare_threshold=0: TAT cache prepared statement phia client. Can thiet
    neu DATABASE_URL tro toi pooler o che do TRANSACTION (PgBouncer transaction
    mode khong ho tro prepared statement xuyen client, se loi "prepared
    statement ... does not exist"). Du an hien dung Session pooler (moi client
    giu nguyen 1 ket noi server nen khong bi gioi han nay), nhung giu
    prepare_threshold=0 cho an toan neu sau nay doi sang transaction mode -
    gan nhu khong ton hieu nang voi so query it cua checkpointer.

    Khong bat except roi fallback im lang o day (khac ban SQLite cu) - neu
    DATABASE_URL sai/thieu hoac Postgres khong ket noi duoc, muon that bai
    ro rang, khong muon lich su chat am tham bien mat nhu bug #7 (xem
    project-memory/FIXED_BUGS.md) tung xay ra. Luu y: vi build lazy, loi chi
    lo ra o lan goi /ask DAU TIEN (khong phai luc khoi dong) - /health van
    xanh du DATABASE_URL cua checkpointer co van de.
    """
    global _checkpointer_pool
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    if not settings.database_url:
        raise ValueError(
            "DATABASE_URL chua duoc cau hinh - AsyncPostgresSaver can Postgres "
            "de luu chat history. Xem .env.example."
        )

    pool = AsyncConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=1,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        check=AsyncConnectionPool.check_connection,
    )
    try:
        await pool.open(wait=True)
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
    except BaseException:
        # Dong pool vua mo roi raise lai nguyen loi - khong nuot loi, chi tranh
        # ro ri pool khi setup() that bai giua chung.
        await pool.close()
        raise
    _checkpointer_pool = pool
    print("[INFO] Checkpointer: AsyncPostgresSaver (Postgres, psycopg pool)", flush=True)
    return saver


async def close_checkpointer() -> None:
    """Dong pool psycopg cua checkpointer luc app shutdown - goi trong
    FastAPI lifespan cua app/api/main.py, cung cho voi repository.close_pool()."""
    global _checkpointer_pool, _rag_app
    if _checkpointer_pool is not None:
        await _checkpointer_pool.close()
        _checkpointer_pool = None
    _rag_app = None


async def _build_rag_app():
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("grade", grade_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("generate", generate_node)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("generate", END)
    graph.add_conditional_edges(
        "grade", decide_after_grade,
        {"generate": "generate", "rewrite": "rewrite"},
    )
    checkpointer = await _get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


async def _get_rag_app():
    global _rag_app
    if _rag_app is not None:
        return _rag_app
    async with _rag_app_lock:
        # Kiem tra lai sau khi co lock - request khac co the vua build xong
        # trong luc request nay dang cho.
        if _rag_app is None:
            _rag_app = await _build_rag_app()
    return _rag_app


# =============================================================================
# PUBLIC API - Interface duy nhat cho FastAPI va Frontend
# =============================================================================

async def ask(question: str, paper_id: str, thread_id: str = "default") -> dict:
    """
    Goi RAG Agent. Cac module khac chi can dung ham nay.

    Voi cung thread_id, Agent tu dong nho lich su cac luot truoc.
    FastAPI se tao thread_id = str(uuid4()) moi cho moi user session.
    """
    app = await _get_rag_app()
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "question": question,
        "paper_id": paper_id,
        "retrieved_chunks": [],
        "grade": "",
        "answer": "",
        "rewrite_count": 0,
        "messages": [],
    }
    return await app.ainvoke(initial_state, config=config)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    async def _main():
        PAPER_ID = "test_cortex_ode"
        THREAD_ID = f"test_{uuid.uuid4().hex[:8]}"

        print("=" * 60, flush=True)
        print("[TEST] LangGraph RAG Agent (Phase 2 - Postgres retrieval)", flush=True)
        print(f"[INFO] Thread ID: {THREAD_ID}", flush=True)
        print("=" * 60, flush=True)

        query1 = "What is CortexODE and how does it use neural ODE for surface reconstruction?"
        print(f"\n[TURN 1] {query1}", flush=True)
        r1 = await ask(question=query1, paper_id=PAPER_ID, thread_id=THREAD_ID)
        print("\n[KET QUA TURN 1]", flush=True)
        print(f"  Grade       : {r1['grade']}", flush=True)
        print(f"  Rewrite     : {r1['rewrite_count']}", flush=True)
        print(f"  Messages    : {len(r1.get('messages', []))}", flush=True)
        print(f"  Tra loi:\n{r1['answer']}", flush=True)

        query2 = "What are the limitations of this approach?"
        print(f"\n{'=' * 60}", flush=True)
        print(f"[TURN 2] {query2}", flush=True)
        print("  (Agent tu dong nho Turn 1 qua thread_id)", flush=True)
        r2 = await ask(question=query2, paper_id=PAPER_ID, thread_id=THREAD_ID)
        print("\n[KET QUA TURN 2]", flush=True)
        print(f"  Rewrite     : {r2['rewrite_count']}", flush=True)
        print(f"  Messages    : {len(r2.get('messages', []))} (nen la 4)", flush=True)
        print(f"  Tra loi:\n{r2['answer']}", flush=True)

        print(f"\n{'=' * 60}", flush=True)
        print("[SUCCESS] Test hoan tat!", flush=True)
        print("=" * 60, flush=True)

    asyncio.run(_main())
