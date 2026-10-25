// Anh de chi huy soat bang mat (khong assert pixel).
import { test } from "@playwright/test";
import { login } from "./helpers";

for (const scheme of ["light", "dark"] as const) {
  test(`screens (${scheme})`, async ({ page }, info) => {
    await page.emulateMedia({ colorScheme: scheme });
    await login(page);
    await page.screenshot({ path: `test-results/shots/${info.project.name}-${scheme}-library.png`, fullPage: true });
    await page.goto("/p/arxiv-1706.03762");
    await page.getByLabel("Câu hỏi").fill("Bản big đạt bao nhiêu BLEU?");
    await page.keyboard.press("Enter");
    await page.locator(".answer-prose strong").waitFor();
    await page.locator(".answer-prose").getByRole("button", { name: /tr\. 2/ }).click();
    if (info.project.name === "mobile") await page.getByRole("button", { name: "Mở trang 2" }).click();
    await page.locator("mark.pdf-mark").first().waitFor({ timeout: 15_000 });
    await page.screenshot({ path: `test-results/shots/${info.project.name}-${scheme}-chat-pdf.png` });
  });
}
