"use client";

import { FileText, Menu, SquarePen } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useShell } from "@/components/app-shell";
import { AssistantMessage, UserMessage } from "@/components/message";
import { Composer } from "@/components/composer";
import { usePapers } from "@/components/papers-context";
import { Thinking } from "@/components/thinking";
import { ApiCallError, api } from "@/lib/client-api";
import { clearChat, loadChat, newThreadId, saveChat, type ChatMessage, type ChatState } from "@/lib/chat-store";
import type { CitationRef } from "@/lib/citations";
import { checkQuestion } from "@/lib/validate";

export interface PdfTarget {
  page: number;
  quote: string;
  section: string;
  token: number;
}

const SUGGESTIONS = [
  "Bài báo này giải quyết vấn đề gì?",
  "Phương pháp chính hoạt động như thế nào?",
  "Kết quả thực nghiệm quan trọng nhất là gì?",
];

const uid = () => crypto.randomUUID();
// Boc Date.now de lint react-hooks/purity khong nham la goi luc render (chi goi trong handler).
const now = () => Date.now();

export function PaperView({ paperId }: { paperId: string }) {
  const { papers, loading } = usePapers();
  const { openSidebar } = useShell();
  const paper = papers.find((p) => p.paper_id === paperId);
  const [chat, setChat] = useState<ChatState | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<{ startedAt: number } | null>(null);
  const [pdfTarget, setPdfTarget] = useState<PdfTarget | null>(null);
  const [pdfOpen, setPdfOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // threadRef = thread_id cua cuoc tro chuyen DANG HIEN (dong bo, khong cho render). Moi ket qua
  // /ask chi duoc ap dung neu thread luc gui van la thread hien tai (tranh tra loi lac sang cuoc khac).
  const threadRef = useRef<string | null>(null);

  useEffect(() => {
    const loaded = loadChat(paperId);
    threadRef.current = loaded.threadId;
    /* eslint-disable react-hooks/set-state-in-effect */
    setChat(loaded); // localStorage chi doc duoc o client -> sau mount
    setDraft("");
    setPending(null);
    setPdfOpen(false);
    setPdfTarget(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    return () => {
      // doi paper / unmount: huy request dang bay
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, [paperId]);

  const update = useCallback(
    (fn: (s: ChatState) => ChatState) =>
      setChat((prev) => {
        if (!prev) return prev;
        const next = fn(prev);
        saveChat(paperId, next);
        return next;
      }),
    [paperId],
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [chat?.messages.length, pending]);

  const send = useCallback(
    async (question: string) => {
      if (!chat || pending || checkQuestion(question)) return;
      const threadId = chat.threadId;
      const applies = () => threadRef.current === threadId;
      const user: ChatMessage = { id: uid(), role: "user", content: question.trim(), createdAt: now() };
      update((s) => ({ ...s, messages: [...s.messages, user] }));
      setDraft("");
      const startedAt = now();
      setPending({ startedAt });
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const res = await api.ask({ question: user.content, paper_id: paperId, thread_id: threadId }, controller.signal);
        if (!applies()) return;
        update((s) => ({
          ...s,
          messages: [...s.messages, {
            id: uid(), role: "assistant", content: res.answer, createdAt: now(), sources: res.sources,
            grade: res.grade, rewriteCount: res.rewrite_count, elapsedMs: now() - startedAt,
          }],
        }));
      } catch (e) {
        if (!applies()) return;
        if (e instanceof DOMException && e.name === "AbortError") {
          update((s) => ({ ...s, messages: [...s.messages, { id: uid(), role: "assistant", content: "", createdAt: now(), stopped: true }] }));
        } else {
          const err = e as ApiCallError;
          update((s) => ({
            ...s,
            messages: [...s.messages, { id: uid(), role: "assistant", content: "", createdAt: now(), error: err.message, question: user.content }],
          }));
          setDraft(user.content); // giu lai cau hoi trong o nhap
        }
      } finally {
        // Request cu (da bi huy) khong duoc xoa trang thai cua request moi.
        if (abortRef.current === controller) {
          abortRef.current = null;
          setPending(null);
        }
      }
    },
    [chat, pending, paperId, update],
  );

  const retry = useCallback(
    (msg: ChatMessage) => {
      if (!msg.question) return;
      update((s) => ({ ...s, messages: s.messages.filter((m) => m.id !== msg.id) }));
      void send(msg.question);
    },
    [update, send],
  );

  const openCitation = useCallback((ref: CitationRef) => {
    setPdfTarget({
      page: ref.source.page_num ?? 1,
      quote: ref.source.text || ref.source.content_preview,
      section: ref.source.section,
      token: now(),
    });
    setPdfOpen(true);
  }, []);

  function newConversation() {
    abortRef.current?.abort();
    abortRef.current = null;
    setPending(null);
    clearChat(paperId);
    const fresh = { threadId: newThreadId(), messages: [] };
    threadRef.current = fresh.threadId;
    setChat(fresh);
    setDraft("");
  }

  const lastUserContent = [...(chat?.messages ?? [])].reverse().find((m) => m.role === "user")?.content;
  const askAgain = useCallback(() => {
    if (lastUserContent) void send(lastUserContent);
  }, [lastUserContent, send]);

  if (!loading && !paper) {
    return (
      <main className="grid h-full place-items-center px-6 text-center">
        <div>
          <p className="font-serif text-[22px] font-semibold">Không tìm thấy bài báo</p>
          <p className="mt-1 text-muted-foreground">Bài có thể đã bị xoá. Chọn một bài khác ở thanh bên.</p>
        </div>
      </main>
    );
  }

  const messages = chat?.messages ?? [];

  return (
    <div className="flex h-full min-w-0">
      <main className="flex min-w-0 flex-1 flex-col md:min-w-[420px]">
        <header className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border px-3 md:px-6">
          <button onClick={openSidebar} aria-label="Mở thư viện" className="grid size-11 place-items-center rounded-[8px] md:hidden">
            <Menu className="size-5" />
          </button>
          <h1 className="min-w-0 flex-1 truncate text-[14px] font-medium">
            {paper?.title ?? " "}
            <span className="ml-2 hidden font-mono text-[12px] font-normal text-faint sm:inline">{paperId}</span>
          </h1>
          {paper?.has_pdf && (
            <button
              onClick={() => {
                setPdfTarget((t) => t ?? { page: 1, quote: "", section: "", token: now() });
                setPdfOpen((o) => !o);
              }}
              className="flex h-11 min-w-11 items-center justify-center gap-1.5 rounded-[6px] border border-border bg-card px-2.5 text-[13px] text-muted-foreground hover:border-border-strong md:h-8 md:min-w-0"
            >
              <FileText className="size-3.5" /> <span className="hidden sm:inline">{pdfOpen ? "Đóng PDF" : "Mở PDF"}</span>
            </button>
          )}
          <button
            onClick={newConversation}
            aria-label="Cuộc trò chuyện mới"
            className="flex h-11 min-w-11 items-center justify-center gap-1.5 rounded-[6px] border border-border bg-card px-2.5 text-[13px] text-muted-foreground hover:border-border-strong md:h-8 md:min-w-0"
          >
            <SquarePen className="size-3.5" /> <span className="hidden sm:inline">Cuộc trò chuyện mới</span>
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 pt-7 md:px-8">
          <div className="mx-auto max-w-[680px] space-y-6 pb-6">
            {chat && messages.length === 0 && (
              <div className="pt-6">
                <p className="font-serif text-[22px] font-semibold leading-snug">{paper?.title}</p>
                <p className="mt-2 text-[14px] text-muted-foreground">Gợi ý để bắt đầu:</p>
                <ul className="mt-2 space-y-1.5">
                  {SUGGESTIONS.map((q) => (
                    <li key={q}>
                      <button onClick={() => void send(q)} className="min-h-11 py-1 text-left text-[15px] text-foreground underline decoration-border-strong underline-offset-4 hover:decoration-foreground md:min-h-6">
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {messages.map((m) =>
              m.role === "user" ? (
                <UserMessage key={m.id} msg={m} />
              ) : (
                <AssistantMessage
                  key={m.id}
                  msg={m}
                  onOpenCitation={openCitation}
                  onRetry={retry}
                  onAskAgain={askAgain}
                />
              ),
            )}
            {pending && <Thinking startedAt={pending.startedAt} />}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="shrink-0 px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-2 md:px-8 md:pb-5">
          <Composer
            value={draft}
            onChange={setDraft}
            onSend={() => void send(draft)}
            onStop={() => abortRef.current?.abort()}
            pending={pending !== null}
            disabled={!chat || !paper}
          />
        </div>
      </main>
      {/* Task 10: <PdfArea …/> renders here when pdfOpen && pdfTarget */}
      {pdfOpen && pdfTarget ? null : null}
    </div>
  );
}
