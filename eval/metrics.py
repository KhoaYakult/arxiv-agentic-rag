"""
eval/metrics.py
================
Logic thuần (không DB, không mạng) cho đánh giá retrieval Phase 3: chuẩn hoá text,
quyết định chunk nào "liên quan", và các metric xếp hạng (Hit@k, MRR, nDCG).

Một chunk được coi là liên quan tới câu hỏi nếu nó chứa bằng chứng (evidence quote)
trong golden set. So khớp trên text đã `norm()` (bỏ ligature, lowercase, chỉ giữ a-z0-9)
vì PDF parser hay làm hỏng khoảng trắng / dấu câu / ligature.

Hai chế độ:
  - strict : norm(quote) là chuỗi con của norm(chunk) cho ít nhất 1 quote.
  - lenient: >= 80% shingle 8 ký tự của norm(quote) xuất hiện trong norm(chunk)
             cho ít nhất 1 quote. Dùng cho bảng số liệu, nơi parser đảo thứ tự ô
             nên strict đếm thiếu.
"""

import math

# Ligature thường gặp trong PDF -> chữ thường để so khớp
_LIGATURES = {
    "ﬁ": "fi",  # ﬁ
    "ﬂ": "fl",  # ﬂ
    "ﬀ": "ff",  # ﬀ
    "ﬃ": "ffi",  # ﬃ
    "ﬄ": "ffl",  # ﬄ
}

SHINGLE_SIZE = 8
LENIENT_THRESHOLD = 0.8
MODES = ("strict", "lenient")
HIT_KS = (1, 3, 5, 10, 20)
MRR_K = 20
NDCG_K = 10


def norm(s: str) -> str:
    """Thay ligature, lowercase, bỏ mọi ký tự không thuộc a-z0-9."""
    for lig, rep in _LIGATURES.items():
        s = s.replace(lig, rep)
    return "".join(ch for ch in s.lower() if ("a" <= ch <= "z") or ("0" <= ch <= "9"))


def shingles(s: str, n: int = SHINGLE_SIZE) -> set[str]:
    """Tập n-gram ký tự của chuỗi (đã norm). Chuỗi ngắn hơn n -> 1 shingle là cả chuỗi."""
    if not s:
        return set()
    if len(s) <= n:
        return {s}
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def is_relevant(
    chunk_text: str,
    quotes: list[str],
    mode: str = "lenient",
    threshold: float = LENIENT_THRESHOLD,
) -> bool:
    """True nếu chunk chứa ít nhất 1 quote theo `mode` ("strict" | "lenient")."""
    if mode not in MODES:
        raise ValueError(f"mode phai la 'strict' hoac 'lenient', nhan duoc {mode!r}")
    chunk_norm = norm(chunk_text)
    chunk_shingles: set[str] | None = None
    for quote in quotes:
        q = norm(quote)
        if not q:
            continue
        if mode == "strict":
            if q in chunk_norm:
                return True
            continue
        if chunk_shingles is None:
            chunk_shingles = shingles(chunk_norm)
        q_shingles = shingles(q)
        if len(q_shingles & chunk_shingles) / len(q_shingles) >= threshold:
            return True
    return False


def first_relevant_rank(rels: list[bool]) -> int | None:
    """Rank (1-based) của chunk liên quan đầu tiên; None nếu không có."""
    for i, r in enumerate(rels, start=1):
        if r:
            return i
    return None


def hit_at_k(rels: list[bool], k: int) -> float:
    """1.0 nếu có ít nhất 1 chunk liên quan trong top k, ngược lại 0.0."""
    return 1.0 if any(rels[:k]) else 0.0


def mrr_at_k(rels: list[bool], k: int = MRR_K) -> float:
    """Reciprocal rank của chunk liên quan đầu tiên trong top k (0 nếu không có)."""
    rank = first_relevant_rank(rels[:k])
    return 1.0 / rank if rank else 0.0


def ndcg_at_k(rels: list[bool], k: int = NDCG_K, ideal_pool: int = 20) -> float:
    """
    nDCG@k với relevance nhị phân. DCG = sum rel_i / log2(i + 1) (i từ 1).
    Ideal DCG: các chunk liên quan nằm hết ở đầu danh sách; số chunk liên quan
    = (số chunk liên quan trong top `ideal_pool` của danh sách retrieve) chặn trên bởi k,
    hoặc 1 nếu không có chunk nào (khi đó DCG = 0 nên nDCG = 0).
    """
    dcg = sum(1.0 / math.log2(i + 1) for i, r in enumerate(rels[:k], start=1) if r)
    n_rel = min(sum(1 for r in rels[:ideal_pool] if r), k)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, max(n_rel, 1) + 1))
    return dcg / ideal


def question_metrics(rels: list[bool]) -> dict[str, float]:
    """Toàn bộ metric của 1 câu hỏi (rels = relevance nhị phân theo thứ tự rank)."""
    out = {f"hit@{k}": hit_at_k(rels, k) for k in HIT_KS}
    out[f"mrr@{MRR_K}"] = mrr_at_k(rels, MRR_K)
    out[f"ndcg@{NDCG_K}"] = ndcg_at_k(rels, NDCG_K)
    return out


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate(per_question: list[dict[str, float]]) -> dict[str, float]:
    """Trung bình từng metric qua các câu hỏi."""
    if not per_question:
        return {}
    return {key: mean([m[key] for m in per_question]) for key in per_question[0]}


def group_mean(
    per_question: list[dict[str, float]],
    group_keys: list[str],
    metric: str,
) -> dict[str, tuple[float, int]]:
    """Trung bình `metric` theo nhóm; trả {nhóm: (giá trị, số câu)}. Hai list song song nhau."""
    buckets: dict[str, list[float]] = {}
    for m, g in zip(per_question, group_keys, strict=True):
        buckets.setdefault(g, []).append(m[metric])
    return {g: (mean(v), len(v)) for g, v in buckets.items()}
