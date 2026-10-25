"use client";

import { MoreHorizontal, Plus, LogOut, PanelLeftClose } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { LibraryError } from "@/components/library-error";
import { usePapers } from "@/components/papers-context";
import { BRAND } from "@/lib/brand";
import { api } from "@/lib/client-api";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import type { Paper } from "@/lib/types";

export function Sidebar({ onNavigate, onCollapse }: { onNavigate?: () => void; onCollapse?: () => void }) {
  const { papers, loading, loaded, error, ingests, dismissIngest, removePaper } = usePapers();
  const params = useParams<{ paperId?: string }>();
  const router = useRouter();
  const activeId = params?.paperId ? decodeURIComponent(params.paperId) : null;
  // target giu lai bai vua chon de tieu de dialog khong bi trong khi dong (animation); open dieu khien hien/an.
  const [target, setTarget] = useState<Paper | null>(null);
  const [open, setOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  // Job xong khi nguoi dung dang o trang khac (khong bi keo di): bao nho, tru bai dang mo.
  const notices = ingests.filter((j) => j.notify && j.paperId !== activeId);

  function askDelete(p: Paper) {
    setTarget(p);
    setDeleteError(null);
    setOpen(true);
  }

  async function confirmDelete() {
    if (!target || deleting) return;
    setDeleteError(null);
    setDeleting(true);
    try {
      await removePaper(target.paper_id);
      if (target.paper_id === activeId) router.replace("/");
      setDeleteError(null);
      setOpen(false);
    } catch (err) {
      setDeleteError((err as Error).message);
    } finally {
      setDeleting(false);
    }
  }

  async function logout() {
    await api.logout().catch(() => undefined);
    router.replace("/login");
  }

  return (
    <aside className="flex h-full w-[264px] flex-col border-r border-border bg-muted px-3 py-4">
      <div className="flex items-center justify-between px-2 pb-4">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-2 text-[15px] font-semibold">
          <span className="grid size-[22px] place-items-center rounded-[6px] bg-primary font-serif text-[14px] text-primary-foreground">
            {BRAND.mark}
          </span>
          {BRAND.name}
        </Link>
        {onCollapse && (
          <button onClick={onCollapse} aria-label="Thu gọn thanh bên" className="grid size-7 place-items-center rounded-[6px] text-faint hover:bg-accent">
            <PanelLeftClose className="size-4" />
          </button>
        )}
      </div>
      <Link
        href="/"
        onClick={onNavigate}
        className="mb-4 flex h-11 items-center gap-2 rounded-[6px] border border-border bg-card px-2.5 text-[14px] font-medium hover:border-border-strong md:h-9"
      >
        <Plus className="size-4" /> Thêm bài báo
      </Link>
      <div className="px-2.5 pb-1.5 text-[12px] text-faint">Thư viện</div>
      {notices.map((j) => (
        <div key={j.key} role="status" className="mx-1 mb-2 flex items-start gap-1 rounded-[6px] border border-border bg-card px-2.5 py-1.5 text-[13px] leading-snug">
          {j.status === "ready" && j.paperId ? (
            <Link
              href={`/p/${encodeURIComponent(j.paperId)}`}
              onClick={() => { dismissIngest(j.key); onNavigate?.(); }}
              className="min-w-0 flex-1 py-1 text-jade underline underline-offset-2"
            >
              {j.title} đã sẵn sàng
            </Link>
          ) : (
            <span className="min-w-0 flex-1 py-1 text-destructive">{j.title}: {j.error}</span>
          )}
          <button
            onClick={() => dismissIngest(j.key)}
            aria-label="Ẩn thông báo"
            className="grid size-11 shrink-0 place-items-center rounded-[6px] text-faint hover:bg-accent md:size-6"
          >
            ×
          </button>
        </div>
      ))}
      <LibraryError className="mx-1 mb-2 px-1.5" />
      <nav className="-mx-1 flex-1 overflow-y-auto px-1" aria-label="Bài báo">
        {loading && <div className="px-2.5 py-2 text-[13px] text-faint">Đang tải…</div>}
        {loaded && !error && papers.length === 0 && <div className="px-2.5 py-2 text-[13px] text-faint">Chưa có bài báo nào</div>}
        {papers.map((p) => {
          const active = p.paper_id === activeId;
          return (
            <div
              key={p.paper_id}
              className={`group relative flex items-start rounded-[6px] ${active ? "bg-card shadow-[inset_0_0_0_1px_var(--border)]" : "hover:bg-accent"}`}
            >
              <Link
                href={`/p/${encodeURIComponent(p.paper_id)}`}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className="min-w-0 flex-1 px-2.5 py-2"
              >
                <span className={`line-clamp-2 text-[14px] leading-snug ${active ? "text-foreground" : "text-muted-foreground"}`}>
                  {p.title}
                </span>
                <span className="mt-0.5 block truncate font-mono text-[12px] text-faint">{p.paper_id}</span>
              </Link>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    aria-label={`Tùy chọn cho ${p.title}`}
                    className="mr-1 mt-1.5 grid size-11 shrink-0 place-items-center rounded-[6px] text-faint opacity-100 hover:bg-accent md:size-7 md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100 md:data-[state=open]:opacity-100"
                  >
                    <MoreHorizontal className="size-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem className="min-h-11 text-destructive md:min-h-0" onSelect={() => askDelete(p)}>
                    Xoá bài báo
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        })}
      </nav>
      <div className="mt-2 flex items-center justify-between border-t border-border px-2.5 pt-3 text-[13px] text-faint">
        <span>{papers.length} bài báo</span>
        <button onClick={logout} className="flex min-h-11 items-center gap-1.5 rounded-[6px] px-1.5 py-1 hover:bg-accent hover:text-foreground md:min-h-6">
          <LogOut className="size-3.5" /> Đăng xuất
        </button>
      </div>

      <AlertDialog open={open} onOpenChange={(o) => { if (!o && !deleting) { setOpen(false); setDeleteError(null); } }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xoá bài báo này?</AlertDialogTitle>
            <AlertDialogDescription>
              “{target?.title}” và mọi đoạn đã lập chỉ mục sẽ bị xoá. Không hoàn tác được.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && <p className="text-[13px] text-destructive">{deleteError}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting} className="h-11 md:h-8">Huỷ</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleting}
              className="h-11 md:h-8"
              onClick={(e) => {
                e.preventDefault();
                void confirmDelete();
              }}
            >
              {deleting ? "Đang xoá…" : "Xoá"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  );
}
