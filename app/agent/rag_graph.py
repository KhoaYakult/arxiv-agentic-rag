"""
app/agent/rag_graph.py - LangGraph RAG Agent (Backend Standard)
Memory tang 1: SqliteSaver (data/chat_memory.db)
Memory tang 2: Upstash Redis - tich hop tai FastAPI (Buoc 5.2)
"""

import sys
import uuid
from pathlib import Path
from typing import Annotated, TypedDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


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


# =============================================================================
# NODES
# =============================================================================

def retrieve_node(state: AgentState) -> dict:
    """Tim kiem Top-5 chunks bang HybridRetriever."""
    from app.indexing.hybrid_retriever import HybridRetriever
    print(f"\n[NODE] retrieve -- {state['question'][:70]}", flush=True)
    retriever = HybridRetriever()
    chunks = retriever.retrieve(
        query=state["question"], paper_id=state["paper_id"], top_k=5, verbose=False
    )
    print(f"[NODE] retrieve -- Tim duoc {len(chunks)} chunks.", flush=True)
    return {"retrieved_chunks": chunks}


def grade_node(state: AgentState) -> dict:
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
    response = chain.invoke({"context": context, "question": state["question"]})
    grade = "yes" if "yes" in response.content.lower().strip() else "no"
    print(f"[NODE] grade -- {grade.upper()} (rewrite={state['rewrite_count']})", flush=True)
    return {"grade": grade}


def rewrite_node(state: AgentState) -> dict:
    """Viet lai cau hoi ro rang hon."""
    from langchain_core.prompts import ChatPromptTemplate
    from app.llm.llm_factory import get_llm
    from app.llm.prompt_templates import REWRITE_QUERY_TEMPLATE

    print(f"[NODE] rewrite -- lan {state['rewrite_count'] + 1}", flush=True)
    chain = ChatPromptTemplate.from_template(REWRITE_QUERY_TEMPLATE) | get_llm()
    response = chain.invoke({"question": state["question"]})
    new_q = response.content.strip()
    print(f"[NODE] rewrite -- moi: {new_q}", flush=True)
    return {"question": new_q, "rewrite_count": state["rewrite_count"] + 1}


def generate_node(state: AgentState) -> dict:
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
    response = chain.invoke({
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
# CHECKPOINTER - Memory Tang 1 (trong phien)
# Tang 2 (Upstash Redis - giua phien) se tich hop tai FastAPI Buoc 5.2
# =============================================================================

def _get_checkpointer():
    try:
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver
        db_path = str(settings.data_dir / "chat_memory.db")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        saver = SqliteSaver(conn)
        print(f"[INFO] Checkpointer: SqliteSaver ({db_path})", flush=True)
        return saver
    except Exception as e:
        from langgraph.checkpoint.memory import MemorySaver
        print(f"[WARN] SqliteSaver loi: {e}. Fallback: MemorySaver.", flush=True)
        return MemorySaver()


# =============================================================================
# BUILD GRAPH
# =============================================================================

def build_rag_graph():
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
    return graph.compile(checkpointer=_get_checkpointer())


rag_app = build_rag_graph()


# =============================================================================
# PUBLIC API - Interface duy nhat cho FastAPI va Frontend
# =============================================================================

def ask(question: str, paper_id: str, thread_id: str = "default") -> dict:
    """
    Goi RAG Agent. Cac module khac chi can dung ham nay.

    Voi cung thread_id, Agent tu dong nho lich su cac luot truoc.
    FastAPI se tao thread_id = str(uuid4()) moi cho moi user session.
    """
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
    return rag_app.invoke(initial_state, config=config)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    PAPER_ID = "test_cortex_ode"
    THREAD_ID = f"test_{uuid.uuid4().hex[:8]}"

    print("=" * 60, flush=True)
    print("[TEST] Buoc 4.3 -- LangGraph RAG Agent", flush=True)
    print(f"[INFO] Thread ID: {THREAD_ID}", flush=True)
    print("=" * 60, flush=True)

    query1 = "What is CortexODE and how does it use neural ODE for surface reconstruction?"
    print(f"\n[TURN 1] {query1}", flush=True)
    r1 = ask(question=query1, paper_id=PAPER_ID, thread_id=THREAD_ID)
    print(f"\n[KET QUA TURN 1]", flush=True)
    print(f"  Grade       : {r1['grade']}", flush=True)
    print(f"  Rewrite     : {r1['rewrite_count']}", flush=True)
    print(f"  Messages    : {len(r1.get('messages', []))}", flush=True)
    print(f"  Tra loi:\n{r1['answer']}", flush=True)

    query2 = "What are the limitations of this approach?"
    print(f"\n{'=' * 60}", flush=True)
    print(f"[TURN 2] {query2}", flush=True)
    print(f"  (Agent tu dong nho Turn 1 qua thread_id)", flush=True)
    r2 = ask(question=query2, paper_id=PAPER_ID, thread_id=THREAD_ID)
    print(f"\n[KET QUA TURN 2]", flush=True)
    print(f"  Rewrite     : {r2['rewrite_count']}", flush=True)
    print(f"  Messages    : {len(r2.get('messages', []))} (nen la 4)", flush=True)
    print(f"  Tra loi:\n{r2['answer']}", flush=True)

    print(f"\n{'=' * 60}", flush=True)
    print("[SUCCESS] Buoc 4.3 hoan tat!", flush=True)
    print("=" * 60, flush=True)
