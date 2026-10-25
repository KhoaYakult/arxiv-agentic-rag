// Cookie phien cho mat khau chung (private beta). Chay o proxy.ts va route handler
// (ca hai deu Node runtime trong Next 16) nen dung node:crypto.
import { createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "pr_session";
export const SESSION_MAX_AGE_S = 60 * 60 * 24 * 30;

function mac(issuedAt: string, secret: string): string {
  return createHmac("sha256", secret).update(`v1.${issuedAt}`).digest("base64url");
}

export function createSessionToken(secret: string, nowMs: number = Date.now()): string {
  const issuedAt = String(Math.floor(nowMs / 1000));
  return `${issuedAt}.${mac(issuedAt, secret)}`;
}

export function verifySessionToken(token: string | undefined, secret: string, nowMs: number = Date.now()): boolean {
  if (!token || !secret) return false;
  const parts = token.split(".");
  if (parts.length !== 2) return false;
  const [issuedAt, given] = parts;
  if (!/^\d{1,12}$/.test(issuedAt) || !given) return false;
  const age = Math.floor(nowMs / 1000) - Number(issuedAt);
  if (age < 0 || age > SESSION_MAX_AGE_S) return false;
  const a = Buffer.from(mac(issuedAt, secret));
  const b = Buffer.from(given);
  return a.length === b.length && timingSafeEqual(a, b);
}

// So sanh hash co do dai co dinh -> timingSafeEqual khong lo do dai mat khau.
export function passwordMatches(input: string, expected: string): boolean {
  if (!expected) return false;
  const h = (s: string) => createHmac("sha256", "pr-password").update(s).digest();
  return timingSafeEqual(h(input), h(expected));
}

export function sessionSecret(): string {
  const s = process.env.SESSION_SECRET ?? "";
  if (s.length < 32) throw new Error("SESSION_SECRET phải dài ít nhất 32 ký tự.");
  return s;
}
