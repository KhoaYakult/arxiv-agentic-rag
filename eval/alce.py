"""
eval/alce.py
=============
Cham trich dan [n] cua cau tra loi theo kieu ALCE (Gao et al., EMNLP 2023, "Enabling Large
Language Models to Generate Text with Citations", arXiv 2305.14627).

Moi CAU cua cau tra loi:
  - co [n]   -> giam khao xem (a) GOP cac doan duoc trich co chung minh cau khong
                (yes/partial/no), (b) TUNG doan rieng le co chung minh khong.
  - khong [n] -> giam khao xem day co phai cau KHANG DINH ve noi dung bai bao khong
                (cau kieu "tai lieu khong co thong tin nay" thi khong can trich dan).

Chi so:
  citation recall    = so cau khang dinh duoc chung minh DAY DU (co [n] va gop doan = yes)
                       / tong so cau khang dinh (co [n] + khang dinh khong [n]).
  citation precision = so trich dan "co ich" / tong so trich dan. Lech so voi ALCE goc: ALCE
                       coi 1 trich dan la thua neu rieng no khong chung minh VA bo no di khong
                       doi ket qua (can them luot "bo tung trich dan"); o day trich dan co ich
                       khi RIENG no chung minh yes hoac partial - partial tinh la co ich, tranh
                       diem yeu da biet cua ALCE (chung minh mot phan bi coi la thua).
  uncited claims     = so cau khang dinh khong co [n].

Giam khao: LLM (mac dinh qwen3.8-27b tren Groq, 1 luot goi / cau tra loi) thay cho model NLI
TRUE (T5-11B) cua ban goc -> so lieu dung de so TRUOC/SAU trong du an, khong so voi bai bao.
"""

import json
import re

from eval import metrics

LABELS = ("yes", "partial", "no")

# Cau ket thuc bang . ! ? (co the kem marker ngay sau) roi khoang trang; hoac xuong dong.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKER_ONLY_RE = re.compile(r"^(\s*\[\d{1,3}(?:\s*[,–-]\s*\d{1,3})*\]\s*)+[.!?]?$")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_MD_RE = re.compile(r"[*_`#>]+")
_MIN_CHARS = 12  # bo tieu de/manh vun ngan ("Tóm lại:", "**Kết quả**")


def strip_markers(text: str) -> str:
    """Bo [n] bang DUNG grammar chung cua eval/metrics.py (khong tao ban sao thu 4 cua regex)."""
    out = re.sub(r"\s+([.,;:!?])", r"\1", metrics._CITATION_RE.sub("", text))
    return re.sub(r"\s{2,}", " ", out)


def split_sentences(answer: str) -> list[str]:
    """Tach cau tra loi thanh cau. Marker dung rieng (vd "... BLEU. [2]") gan vao cau truoc."""
    out: list[str] = []
    for raw in _SENT_SPLIT_RE.split(answer):
        s = _BULLET_RE.sub("", raw).strip()
        if not s:
            continue
        if _MARKER_ONLY_RE.match(s) and out:
            out[-1] = f"{out[-1]} {s}"
            continue
        out.append(s)
    return [s for s in out if len(_MD_RE.sub("", strip_markers(s)).strip()) >= _MIN_CHARS]


def build_items(answer: str, chunks: list[dict]) -> list[dict]:
    """[{i, sentence, cited: [n...]}] - chi giu so [n] trong pham vi so doan."""
    items = []
    for i, s in enumerate(split_sentences(answer), start=1):
        cited = [n for n in metrics.citation_markers(s) if 1 <= n <= len(chunks)]
        items.append({"i": i, "sentence": strip_markers(s).strip(), "cited": cited})
    return items


JUDGE_PROMPT = """You check citations in an answer about a scientific paper.

PASSAGES (numbered as in the answer):
{passages}

SENTENCES TO CHECK:
{sentences}

For every sentence:
- If it has cited passages: "combined" = do ALL its cited passages TOGETHER support everything the sentence states? yes / partial / no. "each" = for EACH cited passage ALONE: yes / partial / no.
- If it has no cited passages: "claim" = true if it states a fact, number or method from the paper; false if it only says the information is missing, asks something, or is a generic remark.
Judge only from the passages, not from your own knowledge. Numbers, model variants and datasets must match exactly; a passage about a different setting is "no".

Return ONLY JSON: {{"results": [{{"i": 1, "combined": "yes", "each": {{"2": "yes", "5": "no"}}}}, {{"i": 2, "claim": false}}]}}"""


def build_prompt(items: list[dict], chunks: list[dict]) -> str:
    used = sorted({n for it in items for n in it["cited"]})
    passages = "\n\n".join(f"[{n}] {chunks[n - 1]['text']}" for n in used) or "(none)"
    lines = []
    for it in items:
        cites = ", ".join(f"[{n}]" for n in it["cited"]) if it["cited"] else "none"
        lines.append(f"{it['i']}. (cited: {cites}) {it['sentence']}")
    return JUDGE_PROMPT.format(passages=passages, sentences="\n".join(lines))


def parse_judgment(text: str) -> dict[int, dict]:
    """JSON cua giam khao -> {i: ket qua}. Chiu duoc ```json ...``` va chu thua quanh JSON."""
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    out = {}
    for r in data.get("results", []) if isinstance(data, dict) else []:
        i = r.get("i") if isinstance(r, dict) else None
        if isinstance(i, str) and i.strip().isdigit():  # model doi khi tra "i": "1"
            i = int(i)
        if isinstance(i, int):
            out[i] = r
    return out


def _label(v) -> str:
    v = str(v).strip().lower()
    return v if v in LABELS else "no"


def score(items: list[dict], judged: dict[int, dict]) -> dict:
    """
    Gop ket qua giam khao thanh so dem. Cau giam khao bo sot -> tinh la khong chung minh.
    Nguoi goi phai loai truoc cau tra loi ma giam khao KHONG doc duoc (judge_ok=False): "khong
    biet" khong duoc dem thanh "sai" (eval 2026-11-17: 4/21 cau bi keo diem vi loi parse).
    """
    claims = supported = partial = uncited = cites = useful = 0
    per_sentence = []
    for it in items:
        r = judged.get(it["i"], {})
        if it["cited"]:
            claims += 1
            combined = _label(r.get("combined"))
            each = r.get("each") if isinstance(r.get("each"), dict) else {}
            labels = {n: _label(each.get(str(n), each.get(n))) for n in it["cited"]}
            supported += combined == "yes"
            partial += combined == "partial"
            cites += len(labels)
            useful += sum(v in ("yes", "partial") for v in labels.values())
            per_sentence.append({**it, "combined": combined, "each": labels})
        else:
            is_claim = r.get("claim") is True
            claims += is_claim
            uncited += is_claim
            per_sentence.append({**it, "claim": is_claim})
    return {"claims": claims, "supported": supported, "partial": partial, "uncited_claims": uncited,
            "citations": cites, "useful_citations": useful, "sentences": per_sentence}


JUDGE_ATTEMPTS = 2


def judge_answer(client, model: str, answer: str, chunks: list[dict]) -> dict:
    """
    1 luot goi LLM cho ca cau tra loi (thu lai 1 lan neu khong doc duoc JSON). client = groq.Groq.
    Ket qua co judge_ok (False = giam khao khong cho ket qua dung dang, KHONG duoc tinh diem) va
    raw (nguyen van lan goi cuoi, de go loi). Loi mang -> raise cho nguoi goi xu ly.
    """
    items = build_items(answer, chunks)
    if not items:
        return {**score([], {}), "judge_ok": True, "raw": ""}
    raw, judged = "", {}
    for _ in range(JUDGE_ATTEMPTS):
        r = client.chat.completions.create(
            model=model, temperature=0, max_tokens=1500, reasoning_effort="none",
            messages=[{"role": "user", "content": build_prompt(items, chunks)}],
        )
        raw = r.choices[0].message.content or ""
        judged = parse_judgment(raw)
        if all(it["i"] in judged for it in items):
            break
    ok = all(it["i"] in judged for it in items)
    return {**score(items, judged), "judge_ok": ok, "raw": raw[:4000]}
