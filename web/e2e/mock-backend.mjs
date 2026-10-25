// Backend FastAPI GIA cho Playwright: cung hinh dang JSON voi app/api/schemas.py.
// Khong goi mang that, khong ton quota. Chay: node e2e/mock-backend.mjs (cong 8799).
import { createServer } from "node:http";
import { readFileSync } from "node:fs";

const PORT = 8799;
const KEY = process.env.APP_API_KEY ?? "test-key";
const pdf = readFileSync(new URL("./fixtures/sample.pdf", import.meta.url));
const papers = new Map([
  ["arxiv-1706.03762", { paper_id: "arxiv-1706.03762", title: "Attention Is All You Need", num_chunks: 107, status: "ready", has_pdf: true }],
  ["old-paper", { paper_id: "old-paper", title: "Old paper without PDF", num_chunks: 12, status: "ready", has_pdf: false }],
]);
const polls = new Map();

const SOURCES = [
  { chunk_id: "c1", section: "6 Results", content_preview: "On the WMT 2014", page_num: 2,
    text: "On the WMT 2014 English-to-French translation task, our big model achieves a BLEU score of 41.0, outperforming all of the previously published single models." },
  { chunk_id: "c2", section: "1 Introduction", content_preview: "Recurrent models", page_num: 1,
    text: "Recurrent models typically factor computation along the symbol positions of the input and output sequences." },
];

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return Buffer.concat(chunks).toString("utf8");
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/files/sample.pdf") {
    res.writeHead(200, { "Content-Type": "application/pdf", "Access-Control-Allow-Origin": "*" });
    return res.end(pdf);
  }
  if (!url.pathname.startsWith("/api/v1/")) return send(res, 404, { detail: "nf" });
  if (req.headers["x-api-key"] !== KEY) return send(res, 401, { detail: "key" });
  const path = url.pathname.slice("/api/v1".length);

  if (req.method === "GET" && path === "/papers") {
    const ready = [...papers.values()].filter((p) => p.status === "ready");
    return send(res, 200, { papers: ready, total: ready.length });
  }
  if (req.method === "POST" && path === "/papers/arxiv") {
    const { arxiv_id } = JSON.parse(await readBody(req));
    const id = `arxiv-${arxiv_id}`;
    papers.set(id, { paper_id: id, title: `Paper ${arxiv_id}`, num_chunks: 0, status: "processing", has_pdf: true });
    polls.set(id, 0);
    return send(res, 202, { paper_id: id, title: `Paper ${arxiv_id}`, status: "processing", num_chunks: 0, message: "" });
  }
  if (req.method === "POST" && path === "/upload") {
    await readBody(req);
    const id = "uploaded-abc123";
    papers.set(id, { paper_id: id, title: "uploaded.pdf", num_chunks: 0, status: "processing", has_pdf: true });
    polls.set(id, 0);
    return send(res, 202, { paper_id: id, title: "uploaded.pdf", status: "processing", num_chunks: 0, message: "" });
  }
  let m = path.match(/^\/papers\/([^/]+)\/status$/);
  if (req.method === "GET" && m) {
    const p = papers.get(m[1]);
    if (!p) return send(res, 404, { detail: "nf" });
    if (p.status === "processing") {
      const n = (polls.get(p.paper_id) ?? 0) + 1;
      polls.set(p.paper_id, n);
      if (n >= 2) Object.assign(p, { status: "ready", num_chunks: 42 });
    }
    return send(res, 200, p);
  }
  m = path.match(/^\/papers\/([^/]+)\/pdf-url$/);
  if (req.method === "GET" && m) {
    const p = papers.get(m[1]);
    if (!p || !p.has_pdf) return send(res, 404, { detail: "no pdf" });
    return send(res, 200, { url: `http://127.0.0.1:${PORT}/files/sample.pdf`, expires_in: 3600 });
  }
  m = path.match(/^\/papers\/([^/]+)$/);
  if (req.method === "DELETE" && m) {
    papers.delete(m[1]);
    return send(res, 204);
  }
  if (req.method === "POST" && path === "/ask") {
    const body = JSON.parse(await readBody(req));
    if (body.question.includes("lỗi quota")) return send(res, 429, { detail: "quota" });
    if (body.question.includes("chậm")) await new Promise((r) => setTimeout(r, 4000));
    const answer = body.question.includes("xss")
      ? "Kết quả <script>window.__xss=1</script><img src=x onerror=\"window.__xss=2\"> **an toàn** [1]"
      : "Bản big đạt **41,0 BLEU** trên Anh–Pháp [1], dựa trên kiến trúc không hồi quy [2]. Số ngoài phạm vi [9] bị ẩn.";
    return send(res, 200, { answer, thread_id: body.thread_id, grade: "yes", rewrite_count: 1, sources: SOURCES });
  }
  return send(res, 404, { detail: "nf" });
}).listen(PORT, "127.0.0.1", () => console.log(`mock backend on ${PORT}`));
