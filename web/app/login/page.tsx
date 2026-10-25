// web/app/login/page.tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { BRAND } from "@/lib/brand";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, next: params.get("next") }),
      });
      const body = await r.json().catch(() => null);
      if (!r.ok) {
        setError(body?.error?.message ?? "Không đăng nhập được. Thử lại.");
        return;
      }
      router.replace(body.next ?? "/");
      router.refresh();
    } catch {
      setError("Không kết nối được máy chủ. Kiểm tra mạng và thử lại.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="w-full max-w-[340px]">
      <span className="inline-grid size-7 place-items-center rounded-[7px] bg-primary font-serif text-[16px] font-semibold text-primary-foreground">
        {BRAND.mark}
      </span>
      <h1 className="mt-4 font-serif text-[26px] font-semibold">{BRAND.name}</h1>
      <p className="mt-1.5 text-[14px] leading-relaxed text-muted-foreground">
        Bản dùng thử riêng. Nhập mật khẩu được chia sẻ cho bạn.
      </p>
      <label htmlFor="password" className="sr-only">Mật khẩu</label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        autoFocus
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="mt-5 h-11 w-full rounded-[8px] border border-border-strong bg-card px-3 text-[16px] outline-none focus-visible:ring-2 focus-visible:ring-ring"
        placeholder="Mật khẩu"
      />
      <button
        type="submit"
        disabled={busy || !password}
        className="mt-2.5 h-11 w-full rounded-[8px] bg-primary text-[14px] font-medium text-primary-foreground transition-opacity disabled:opacity-50"
      >
        {busy ? "Đang vào…" : "Vào"}
      </button>
      <p role="alert" className="mt-2 min-h-5 text-[13px] text-destructive">{error}</p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
