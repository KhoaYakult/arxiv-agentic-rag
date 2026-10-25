import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("ask, see chips, hover quote, open PDF at the cited page with highlight", async ({ page, isMobile }) => {
  await login(page, "/p/arxiv-1706.03762");
  await page.getByLabel("Câu hỏi").fill("Bản big đạt bao nhiêu BLEU?");
  await page.keyboard.press("Enter");
  await expect(page.locator(".answer-prose strong")).toHaveText("41,0 BLEU");
  await expect(page.getByText("Đã đọc 2 đoạn · viết lại câu hỏi 1 lần")).toBeVisible();
  await expect(page.getByText("[9]")).toHaveCount(0);
  const chip = page.locator(".answer-prose").getByRole("button", { name: /tr\. 2/ });
  if (isMobile) {
    await chip.click();
    await expect(page.getByText("6 Results · trang 2")).toBeVisible();
    await page.getByRole("button", { name: "Mở trang 2" }).click();
  } else {
    await chip.hover();
    await expect(page.getByText("Mở trang 2 →")).toBeVisible();
    await chip.click();
  }
  await expect(page.getByLabel("Bản PDF")).toBeVisible();
  await expect(page.getByText(/tr\. 2 \/ 2/)).toBeVisible();
  await expect(page.locator("mark.pdf-mark").first()).toBeVisible({ timeout: 15_000 });
});

test("HTML in answers never executes", async ({ page }) => {
  await login(page, "/p/arxiv-1706.03762");
  await page.getByLabel("Câu hỏi").fill("thử xss nhé");
  await page.keyboard.press("Enter");
  await expect(page.locator(".answer-prose strong")).toHaveText("an toàn");
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  await expect(page.locator(".answer-prose script, .answer-prose img")).toHaveCount(0);
});

test("IME composition Enter does not send", async ({ page }) => {
  await login(page, "/p/arxiv-1706.03762");
  const box = page.getByLabel("Câu hỏi");
  await box.fill("Bài này nói gì");
  await box.dispatchEvent("keydown", { key: "Enter", isComposing: true, keyCode: 229 });
  await expect(page.getByText("Bài này nói gì").and(page.locator(".bg-user-bubble"))).toHaveCount(0);
  await expect(box).toHaveValue("Bài này nói gì");
  // Doi chung: Enter that su (khong IME) van gui duoc -> bong bong nguoi dung xuat hien.
  await page.keyboard.press("Enter");
  await expect(page.getByText("Bài này nói gì").and(page.locator(".bg-user-bubble"))).toHaveCount(1);
});

test("stop cancels a slow answer", async ({ page }) => {
  await login(page, "/p/arxiv-1706.03762");
  await page.getByLabel("Câu hỏi").fill("trả lời chậm thôi");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Đang tìm và đọc các đoạn liên quan trong bài…")).toBeVisible();
  await page.getByRole("button", { name: "Dừng" }).click();
  await expect(page.getByText("Đã dừng.")).toBeVisible();
  // Cho qua han mock tra loi (4 giay): ket qua cu khong duoc hien sau khi da Dung.
  await page.waitForTimeout(4500);
  await expect(page.locator(".answer-prose")).toHaveCount(0);
});

test("429 shows the quota message and keeps the question in the composer", async ({ page }) => {
  await login(page, "/p/arxiv-1706.03762");
  await page.getByLabel("Câu hỏi").fill("gây lỗi quota đi");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Hết lượt xử lý miễn phí hôm nay. Hãy thử lại sau 14:00.")).toBeVisible();
  await expect(page.getByLabel("Câu hỏi")).toHaveValue("gây lỗi quota đi");
});

test("paper with PDF shows the Mở PDF button (positive control)", async ({ page }) => {
  await login(page, "/p/arxiv-1706.03762");
  await expect(page.getByRole("heading", { name: /Attention Is All You Need/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mở PDF" })).toBeVisible();
});

test("paper without PDF: no Mở PDF button, chip says no PDF", async ({ page }) => {
  await login(page, "/p/old-paper");
  // Nut chi hien sau khi paper tai xong -> doi tieu de truoc, neu khong count 0 se dung sai ngay lap tuc.
  await expect(page.getByRole("heading", { name: /Old paper without PDF/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Mở PDF|Đóng PDF/ })).toHaveCount(0);
  await page.getByLabel("Câu hỏi").fill("Bài này nói gì vậy?");
  await page.keyboard.press("Enter");
  await page.locator(".answer-prose").getByRole("button", { name: /tr\. 2/ }).click();
  await expect(page.getByText("Bài này không có bản PDF gốc.")).toBeVisible();
});
