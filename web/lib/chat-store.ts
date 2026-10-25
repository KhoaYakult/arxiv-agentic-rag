// Luu hoi thoai theo tung paper trong localStorage (tai lai trang van thay). Tri nho cho
// LLM van o server (thread_id -> LangGraph checkpointer). Moi doc/ghi deu chiu loi.
import type { Source } from "@/lib/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  sources?: Source[];
  grade?: "yes" | "no";
  rewriteCount?: number;
  elapsedMs?: number;
  error?: string;
  question?: string; // cau hoi goc cua 1 tin nhan loi -> nut "Thu lai"
  stopped?: boolean;
}

export interface ChatState {
  threadId: string;
  messages: ChatMessage[];
}

const key = (paperId: string) => `pr:chat:${paperId}`;

export function newThreadId(): string {
  return `web_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
}

function defaultStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function loadChat(paperId: string, storage: Storage | null = defaultStorage()): ChatState {
  try {
    const raw = storage?.getItem(key(paperId));
    if (raw) {
      const parsed = JSON.parse(raw) as ChatState;
      if (typeof parsed.threadId === "string" && Array.isArray(parsed.messages)) return parsed;
    }
  } catch {
    // du lieu hong / bi chan: bat dau cuoc moi
  }
  return { threadId: newThreadId(), messages: [] };
}

export function saveChat(paperId: string, state: ChatState, storage: Storage | null = defaultStorage()): void {
  try {
    storage?.setItem(key(paperId), JSON.stringify(state));
  } catch {
    // het quota / bi chan: bo qua, app van chay
  }
}

export function clearChat(paperId: string, storage: Storage | null = defaultStorage()): void {
  try {
    storage?.removeItem(key(paperId));
  } catch {
    // bo qua
  }
}
