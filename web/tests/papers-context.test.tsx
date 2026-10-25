// @vitest-environment jsdom
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const papersMock = vi.fn();
const importArxivMock = vi.fn();
const statusMock = vi.fn();
const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), pathname: "/" }));

vi.mock("next/navigation", () => ({
  useRouter: () => nav, // doi tuong on dinh nhu Next that (khong tao moi moi lan render)
  usePathname: () => nav.pathname,
}));
vi.mock("@/lib/client-api", () => {
  class ApiCallError extends Error {
    constructor(public code: string, message: string, public status: number) {
      super(message);
    }
  }
  return {
    ApiCallError,
    api: {
      papers: (...a: unknown[]) => papersMock(...a),
      importArxiv: (...a: unknown[]) => importArxivMock(...a),
      status: (...a: unknown[]) => statusMock(...a),
    },
  };
});

import { PapersProvider, usePapers } from "@/components/papers-context";
import { ApiCallError } from "@/lib/client-api";

function Probe() {
  const { offline, papers, error, loaded, ingests, startArxiv } = usePapers();
  return (
    <div>
      <p data-testid="s">{offline ? "offline" : `online:${papers.length}`}</p>
      <p data-testid="err">{error ?? "-"}</p>
      <p data-testid="loaded">{String(loaded)}</p>
      <p data-testid="jobs">{ingests.map((j) => `${j.status}:${j.notify ? "notify" : "quiet"}`).join(",")}</p>
      <button onClick={() => void startArxiv("2401.00001")}>start</button>
    </div>
  );
}

const down = () => Promise.reject(new ApiCallError("backend_down", "x", 0));

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  papersMock.mockReset();
  importArxivMock.mockReset();
  statusMock.mockReset();
  nav.push.mockReset();
  nav.pathname = "/";
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

describe("PapersProvider loading errors", () => {
  it("exposes a non-network /papers failure as error and keeps loaded false", async () => {
    papersMock.mockRejectedValue(new ApiCallError("server_error", "Máy chủ gặp lỗi. Hãy thử lại.", 500));
    render(<PapersProvider><Probe /></PapersProvider>);
    await act(async () => {});
    expect(screen.getByTestId("err").textContent).toBe("Máy chủ gặp lỗi. Hãy thử lại.");
    expect(screen.getByTestId("loaded").textContent).toBe("false");
    expect(screen.getByTestId("s").textContent).toBe("online:0"); // khong phai offline

    // Thu lai thanh cong -> loaded true, het loi.
    papersMock.mockResolvedValue({ papers: [], total: 0 });
    // refresh() duoc goi qua nut "Thu lai" trong UI; o day dung su kien online (cung goi refresh).
    await act(async () => { window.dispatchEvent(new Event("online")); });
    expect(screen.getByTestId("err").textContent).toBe("-");
    expect(screen.getByTestId("loaded").textContent).toBe("true");
  });
});

describe("PapersProvider auto-navigation after ingest", () => {
  async function runIngest(pathname: string) {
    nav.pathname = pathname;
    papersMock.mockResolvedValue({ papers: [], total: 0 });
    importArxivMock.mockResolvedValue({ paper_id: "x", title: "X", status: "processing", num_chunks: 0, message: "" });
    statusMock.mockResolvedValue({ paper_id: "x", title: "X", status: "ready" });
    render(<PapersProvider><Probe /></PapersProvider>);
    await act(async () => {});
    await act(async () => { screen.getByText("start").click(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  }

  it("navigates to the new paper when the user is on the home page", async () => {
    await runIngest("/");
    expect(nav.push).toHaveBeenCalledWith("/p/x");
    expect(screen.getByTestId("jobs").textContent).toBe("ready:quiet");
  });

  it("does not navigate from another page; marks the job for a sidebar notice instead", async () => {
    await runIngest("/p/other");
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.getByTestId("jobs").textContent).toBe("ready:notify");
  });

  it("surfaces a failed ingest as a notice when not on the home page", async () => {
    nav.pathname = "/p/other";
    papersMock.mockResolvedValue({ papers: [], total: 0 });
    importArxivMock.mockResolvedValue({ paper_id: "x", title: "X", status: "processing", num_chunks: 0, message: "" });
    statusMock.mockResolvedValue({ paper_id: "x", title: "X", status: "failed" });
    render(<PapersProvider><Probe /></PapersProvider>);
    await act(async () => {});
    await act(async () => { screen.getByText("start").click(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.getByTestId("jobs").textContent).toBe("failed:notify");
  });
});
