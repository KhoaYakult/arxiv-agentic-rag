"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { ApiCallError, api } from "@/lib/client-api";
import type { Paper, UploadResult } from "@/lib/types";

export interface IngestJob {
  key: string;
  paperId: string | null;
  title: string;
  status: "sending" | "processing" | "ready" | "failed";
  error?: string;
  startedAt: number;
  // true = job xong khi nguoi dung KHONG o trang chu (khong tu chuyen trang) -> sidebar hien thong bao nho.
  notify?: boolean;
}

interface PapersValue {
  papers: Paper[];
  loading: boolean;
  // true sau lan tai /papers dau tien thanh cong: phan biet "thu vien trong" voi "chua tai duoc".
  loaded: boolean;
  error: string | null;
  offline: boolean;
  refresh: () => Promise<void>;
  ingests: IngestJob[];
  startUpload: (file: File) => Promise<void>;
  startArxiv: (arxivId: string) => Promise<void>;
  dismissIngest: (key: string) => void;
  removePaper: (paperId: string) => Promise<void>;
}

const PapersContext = createContext<PapersValue | null>(null);
const POLL_MS = 2000;
const POLL_LIMIT_MS = 10 * 60 * 1000;
// Backend danh dau 'ready' truoc khi set has_pdf=true (PDF upload ngay sau do) -> refresh them 1 lan.
const HAS_PDF_REFRESH_MS = 5000;
const FAILED_MESSAGE =
  "Xử lý thất bại. Nguyên nhân thường gặp: dịch vụ AI đang quá tải hoặc đã hết lượt miễn phí (hãy thử lại sau ít phút; nếu vẫn lỗi, lượt miễn phí sẽ được cấp lại vào khoảng 14–15 giờ chiều), hoặc PDF không đọc được.";

export function usePapers(): PapersValue {
  const v = useContext(PapersContext);
  if (!v) throw new Error("usePapers phải nằm trong <PapersProvider>");
  return v;
}

export function PapersProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  // Poll chay trong interval dai han -> doc pathname hien tai qua ref, khong de no vao deps.
  const pathnameRef = useRef(pathname);
  useEffect(() => {
    pathnameRef.current = pathname;
  }, [pathname]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  // Dem so lan that bai lien tiep: doi gia tri de effect backoff tu hen lai lan nua khi offline van true.
  const [failures, setFailures] = useState(0);
  const [ingests, setIngests] = useState<IngestJob[]>([]);
  const retryDelay = useRef(2000);
  const lateRefreshTimers = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  const refresh = useCallback(async () => {
    try {
      const { papers } = await api.papers();
      setPapers(papers);
      setLoaded(true);
      setError(null);
      setOffline(false);
      setFailures(0);
      retryDelay.current = 2000;
    } catch (e) {
      const err = e as ApiCallError;
      if (err.code === "backend_down" || err.code === "timeout") {
        setOffline(true);
        setFailures((n) => n + 1);
        setError(null); // banner offline da bao roi
      } else setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Tai danh sach luc mount: setState chi chay sau await nen khong gay render day chuyen.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  // Don timer refresh tre khi unmount.
  useEffect(() => {
    const timers = lateRefreshTimers.current;
    return () => {
      timers.forEach(clearTimeout);
      timers.clear();
    };
  }, []);

  const refreshLater = useCallback(() => {
    const t = setTimeout(() => {
      lateRefreshTimers.current.delete(t);
      void refresh();
    }, HAS_PDF_REFRESH_MS);
    lateRefreshTimers.current.add(t);
  }, [refresh]);

  // Mat ket noi: thu lai voi backoff 2s -> 4s -> ... -> 30s.
  useEffect(() => {
    if (!offline) return;
    const t = setTimeout(() => {
      retryDelay.current = Math.min(retryDelay.current * 2, 30_000);
      void refresh();
    }, retryDelay.current);
    return () => clearTimeout(t);
  }, [offline, failures, refresh]);

  useEffect(() => {
    const goOffline = () => setOffline(true);
    const goOnline = () => void refresh();
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    return () => {
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
    };
  }, [refresh]);

  const patch = useCallback(
    (key: string, p: Partial<IngestJob>) => setIngests((list) => list.map((j) => (j.key === key ? { ...j, ...p } : j))),
    [],
  );

  // Chi tu chuyen sang bai moi khi nguoi dung dang o trang chu; o trang khac thi bao bang notify.
  const onTrangChu = useCallback(() => pathnameRef.current === "/", []);

  const onAccepted = useCallback(
    async (key: string, res: UploadResult) => {
      if (res.status === "ready") {
        patch(key, { paperId: res.paper_id, title: res.title, status: "ready" });
        await refresh();
        if (onTrangChu()) router.push(`/p/${encodeURIComponent(res.paper_id)}`);
        else patch(key, { notify: true });
        return;
      }
      patch(key, { paperId: res.paper_id, title: res.title, status: "processing" });
    },
    [patch, refresh, router, onTrangChu],
  );

  const start = useCallback(
    async (title: string, send: () => Promise<UploadResult>) => {
      const key = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setIngests((list) => [{ key, paperId: null, title, status: "sending", startedAt: Date.now() }, ...list]);
      try {
        await onAccepted(key, await send());
      } catch (e) {
        patch(key, { status: "failed", error: (e as ApiCallError).message });
      }
    },
    [onAccepted, patch],
  );

  const startUpload = useCallback((file: File) => start(file.name, () => api.upload(file)), [start]);
  const startArxiv = useCallback((id: string) => start(`arXiv ${id}`, () => api.importArxiv(id)), [start]);
  const dismissIngest = useCallback((key: string) => setIngests((list) => list.filter((j) => j.key !== key)), []);

  // Poll status cua cac job dang 'processing'. finished: tranh xu ly 2 lan khi 2 vong poll chong nhau.
  const finished = useRef<Set<string>>(new Set());
  useEffect(() => {
    const active = ingests.filter((j) => j.status === "processing" && j.paperId);
    if (!active.length) return;
    const t = setInterval(async () => {
      for (const job of active) {
        if (finished.current.has(job.key)) continue;
        if (Date.now() - job.startedAt > POLL_LIMIT_MS) {
          finished.current.add(job.key);
          patch(job.key, { status: "failed", error: "Quá thời gian chờ xử lý (10 phút).", notify: !onTrangChu() });
          continue;
        }
        try {
          const s = await api.status(job.paperId!);
          if (finished.current.has(job.key)) continue;
          if (s.status === "ready") {
            finished.current.add(job.key);
            patch(job.key, { status: "ready", title: s.title });
            await refresh();
            refreshLater();
            if (onTrangChu()) router.push(`/p/${encodeURIComponent(s.paper_id)}`);
            else patch(job.key, { notify: true });
          } else if (s.status === "failed") {
            finished.current.add(job.key);
            patch(job.key, { status: "failed", error: FAILED_MESSAGE, notify: !onTrangChu() });
          }
        } catch {
          // loi mang tam thoi: lan poll sau thu lai
        }
      }
    }, POLL_MS);
    return () => clearInterval(t);
  }, [ingests, patch, refresh, refreshLater, router, onTrangChu]);

  const removePaper = useCallback(
    async (paperId: string) => {
      await api.remove(paperId);
      try {
        window.localStorage.removeItem(`pr:chat:${paperId}`);
      } catch {
        // localStorage bi chan: bo qua
      }
      await refresh();
    },
    [refresh],
  );

  return (
    <PapersContext.Provider
      value={{ papers, loading, loaded, error, offline, refresh, ingests, startUpload, startArxiv, dismissIngest, removePaper }}
    >
      {children}
    </PapersContext.Provider>
  );
}
