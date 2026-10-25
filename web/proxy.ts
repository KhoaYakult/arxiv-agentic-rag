// Chan moi trang va /api/* khi chua co cookie phien hop le (Next 16: "proxy" thay "middleware").
import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/session";

const PUBLIC_PATHS = new Set(["/login", "/api/login"]);

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();
  const ok = verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value, process.env.SESSION_SECRET ?? "");
  if (ok) return NextResponse.next();
  if (pathname.startsWith("/api/")) {
    return NextResponse.json(
      { error: { code: "unauthorized", message: "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại." } },
      { status: 401 },
    );
  }
  const url = new URL("/login", request.url);
  url.searchParams.set("next", pathname + search);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|robots.txt).*)"],
};
