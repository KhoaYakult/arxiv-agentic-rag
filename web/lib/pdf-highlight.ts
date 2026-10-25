// Tim doan trich (text cua chunk) trong text layer cua 1 trang PDF (pdf.js text items).
// Chuan hoa ca hai ben: NFKC (ligature), lowercase, bo ky tu markdown (*_#|`>), gop khoang
// trang, noi tu bi ngat dong bang gach noi. Thu khop dau doan (dai -> ngan), roi cuoi doan
// (chunk bat dau o trang truoc). Tra ve tap chi so item can to, hoac null.
const STRIP_RE = /[*_#|`>]/g;
const LETTER = /[a-zÀ-ɏḀ-ỿ]/;

// Gach noi giua hai chu cai bi bo han o CA HAI ben ("English-to-" + "French" ngat dong va
// "English-to-French" trong chunk deu thanh "englishtofrench"), nen khop duoc ca hai kieu.
const INNER_HYPHEN_RE = /(?<=[a-zÀ-ɏḀ-ỿ])-(?=[a-zÀ-ɏḀ-ỿ])/g;

function norm(s: string): string {
  return s.normalize("NFKC").toLowerCase().replace(STRIP_RE, " ").replace(INNER_HYPHEN_RE, "").replace(/\s+/g, " ");
}

function buildHaystack(items: string[]): { hay: string; owner: number[] } {
  let hay = "";
  const owner: number[] = [];
  items.forEach((raw, idx) => {
    const t = norm(raw).trim();
    if (!t) return;
    if (hay) {
      const prev = hay[hay.length - 2] ?? "";
      if (hay.endsWith("-") && LETTER.test(prev) && LETTER.test(t[0])) {
        hay = hay.slice(0, -1); // "repre-" + "sentation" -> "representation"
        owner.pop();
      } else {
        hay += " ";
        owner.push(-1);
      }
    }
    for (let i = 0; i < t.length; i++) {
      hay += t[i];
      owner.push(idx);
    }
  });
  return { hay, owner };
}

function normQuote(q: string): string {
  return norm(q)
    .replace(/([a-zÀ-ɏḀ-ỿ])- (?=[a-zÀ-ɏḀ-ỿ])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function collect(owner: number[], from: number, to: number): Set<number> | null {
  const out = new Set<number>();
  for (let i = from; i < to; i++) if (owner[i] >= 0) out.add(owner[i]);
  return out.size ? out : null;
}

export function findHighlight(items: string[], quote: string, minLen = 40): Set<number> | null {
  if (!items.length || !quote) return null;
  const { hay, owner } = buildHaystack(items);
  const q = normQuote(quote);
  if (!hay || q.length < 10) return null;
  const floor = Math.min(minLen, q.length);

  for (let len = Math.min(q.length, 160); len >= floor; len -= 20) {
    // 1) Dau doan
    const head = q.slice(0, len).trim();
    let pos = hay.indexOf(head);
    if (pos >= 0) {
      let k = head.length;
      while (pos + k < hay.length && k < q.length && hay[pos + k] === q[k]) k++;
      return collect(owner, pos, pos + k);
    }
    // 2) Cuoi doan
    const tail = q.slice(q.length - len).trim();
    pos = hay.indexOf(tail);
    if (pos >= 0) {
      const qStart = q.length - tail.length;
      let back = 0;
      while (pos - back - 1 >= 0 && qStart - back - 1 >= 0 && hay[pos - back - 1] === q[qStart - back - 1]) back++;
      return collect(owner, pos - back, pos + tail.length);
    }
  }
  return null;
}
