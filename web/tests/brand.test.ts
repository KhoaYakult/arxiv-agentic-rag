// web/tests/brand.test.ts
import { describe, expect, it } from "vitest";
import { BRAND } from "@/lib/brand";

describe("BRAND", () => {
  it("has a name and a one-letter mark", () => {
    expect(BRAND.name.length).toBeGreaterThan(0);
    expect(BRAND.mark).toHaveLength(1);
  });
});
