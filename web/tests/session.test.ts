import { describe, expect, it } from "vitest";
import {
  SESSION_MAX_AGE_S, createSessionToken, passwordMatches, sessionSecret, verifySessionToken,
} from "@/lib/session";

const SECRET = "x".repeat(40);
const NOW = 1_800_000_000_000;

describe("session token", () => {
  it("round-trips", () => {
    const t = createSessionToken(SECRET, NOW);
    expect(t).toMatch(/^\d+\.[A-Za-z0-9_-]+$/);
    expect(verifySessionToken(t, SECRET, NOW + 1000)).toBe(true);
  });
  it("rejects wrong secret, tampering, garbage and empty secret", () => {
    const t = createSessionToken(SECRET, NOW);
    expect(verifySessionToken(t, "y".repeat(40), NOW)).toBe(false);
    const [iat, mac] = t.split(".");
    expect(verifySessionToken(`${Number(iat) + 1}.${mac}`, SECRET, NOW)).toBe(false);
    expect(verifySessionToken("abc", SECRET, NOW)).toBe(false);
    expect(verifySessionToken(`${t}.extra`, SECRET, NOW)).toBe(false);
    expect(verifySessionToken(undefined, SECRET, NOW)).toBe(false);
    expect(verifySessionToken(t, "", NOW)).toBe(false);
  });
  it("expires after 30 days and rejects future tokens", () => {
    const t = createSessionToken(SECRET, NOW);
    expect(verifySessionToken(t, SECRET, NOW + SESSION_MAX_AGE_S * 1000 + 1000)).toBe(false);
    expect(verifySessionToken(createSessionToken(SECRET, NOW + 60_000), SECRET, NOW)).toBe(false);
  });
});

describe("passwordMatches", () => {
  it("compares exactly and never matches an empty expected password", () => {
    expect(passwordMatches("hunter2", "hunter2")).toBe(true);
    expect(passwordMatches("hunter3", "hunter2")).toBe(false);
    expect(passwordMatches("", "")).toBe(false);
  });
});

describe("sessionSecret", () => {
  it("throws when shorter than 32 chars", () => {
    process.env.SESSION_SECRET = "short";
    expect(() => sessionSecret()).toThrow();
    process.env.SESSION_SECRET = SECRET;
    expect(sessionSecret()).toBe(SECRET);
  });
});
