// @vitest-environment jsdom
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const papersMock = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/lib/client-api", () => {
  class ApiCallError extends Error {
    constructor(public code: string, message: string, public status: number) {
      super(message);
    }
  }
  return { ApiCallError, api: { papers: (...a: unknown[]) => papersMock(...a) } };
});

import { PapersProvider, usePapers } from "@/components/papers-context";
import { ApiCallError } from "@/lib/client-api";

function Probe() {
  const { offline, papers } = usePapers();
  return <p data-testid="s">{offline ? "offline" : `online:${papers.length}`}</p>;
}

const down = () => Promise.reject(new ApiCallError("backend_down", "x", 0));

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  papersMock.mockReset();
});

describe("PapersProvider offline backoff", () => {
  it("keeps retrying with 2s, 4s, 8s while the backend stays down, then recovers", async () => {
    papersMock.mockImplementation(down);
    render(<PapersProvider><Probe /></PapersProvider>);
    await act(async () => {}); // refresh luc mount
    expect(papersMock).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("s").textContent).toBe("offline");

    await act(async () => { await vi.advanceTimersByTimeAsync(1999); });
    expect(papersMock).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(papersMock).toHaveBeenCalledTimes(2);

    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(papersMock).toHaveBeenCalledTimes(3);
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(papersMock).toHaveBeenCalledTimes(4);
    expect(screen.getByTestId("s").textContent).toBe("offline");

    // Backend song lai: lan thu ke tiep (sau 16s) thanh cong -> het offline, ngung thu.
    papersMock.mockResolvedValue({ papers: [], total: 0 });
    await act(async () => { await vi.advanceTimersByTimeAsync(16_000); });
    expect(papersMock).toHaveBeenCalledTimes(5);
    expect(screen.getByTestId("s").textContent).toBe("online:0");
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(papersMock).toHaveBeenCalledTimes(5);
  });
});
