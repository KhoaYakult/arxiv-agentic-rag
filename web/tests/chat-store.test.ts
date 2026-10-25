import { describe, expect, it } from "vitest";
import { clearChat, loadChat, newThreadId, saveChat } from "@/lib/chat-store";

function memoryStorage(): Storage {
  const m = new Map<string, string>();
  return {
    getItem: (k) => m.get(k) ?? null,
    setItem: (k, v) => void m.set(k, v),
    removeItem: (k) => void m.delete(k),
    clear: () => m.clear(),
    key: () => null,
    get length() { return m.size; },
  } as Storage;
}

describe("chat-store", () => {
  it("round-trips per paper", () => {
    const s = memoryStorage();
    const state = { threadId: "web_abc", messages: [{ id: "1", role: "user" as const, content: "hi", createdAt: 1 }] };
    saveChat("p1", state, s);
    expect(loadChat("p1", s)).toEqual(state);
    expect(loadChat("p2", s).messages).toEqual([]);
    clearChat("p1", s);
    expect(loadChat("p1", s).messages).toEqual([]);
  });
  it("survives missing storage and corrupt data", () => {
    expect(loadChat("p", null).messages).toEqual([]);
    expect(() => saveChat("p", { threadId: "t", messages: [] }, null)).not.toThrow();
    const s = memoryStorage();
    s.setItem("pr:chat:p", "{not json");
    expect(loadChat("p", s).messages).toEqual([]);
  });
  it("thread ids match the backend-safe pattern", () => {
    expect(newThreadId()).toMatch(/^web_[A-Za-z0-9_-]{8,40}$/);
  });
});
