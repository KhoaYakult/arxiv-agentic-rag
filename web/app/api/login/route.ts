import { NextResponse } from "next/server";
import { apiError } from "@/lib/backend";
import { SESSION_COOKIE, SESSION_MAX_AGE_S, createSessionToken, passwordMatches, sessionSecret } from "@/lib/session";
import { safeNextPath } from "@/lib/validate";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { password?: unknown; next?: unknown } | null;
  const password = typeof body?.password === "string" ? body.password : "";
  if (!passwordMatches(password, process.env.ACCESS_PASSWORD ?? "")) {
    await new Promise((r) => setTimeout(r, 500)); // lam cham do mat khau
    return apiError("bad_password", 401);
  }
  const res = NextResponse.json({ ok: true, next: safeNextPath(typeof body?.next === "string" ? body.next : null) });
  res.cookies.set(SESSION_COOKIE, createSessionToken(sessionSecret()), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  });
  return res;
}
