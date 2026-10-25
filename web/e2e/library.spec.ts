import { expect, test } from "@playwright/test";
import { appAlert, login } from "./helpers";

test("arXiv import walks through progress and opens the paper", async ({ page }) => {
  await login(page);
  await page.getByLabel("Nhập từ arXiv").fill("https://arxiv.org/abs/2401.15884");
  await page.getByRole("button", { name: "Thêm" }).click();
  await expect(page.getByText("Đọc, tách đoạn và lập chỉ mục")).toBeVisible();
  await expect(page).toHaveURL(/\/p\/arxiv-2401.15884$/, { timeout: 15_000 });
  await expect(page.getByRole("navigation", { name: "Bài báo" }).getByText("Paper 2401.15884")).toBeVisible();
});

test("oversized and non-PDF files are rejected client-side", async ({ page }) => {
  await login(page);
  await page.getByLabel("Chọn file PDF").setInputFiles({ name: "a.pdf", mimeType: "application/pdf", buffer: Buffer.from("hello") });
  await expect(appAlert(page)).toContainText("không phải PDF");
  await page.getByLabel("Chọn file PDF").setInputFiles({
    name: "big.pdf", mimeType: "application/pdf", buffer: Buffer.concat([Buffer.from("%PDF"), Buffer.alloc(4 * 1024 * 1024)]),
  });
  await expect(appAlert(page)).toContainText("lớn hơn 4 MB");
});

test("delete asks for confirmation", async ({ page }) => {
  await login(page);
  // Tao 1 paper rieng cho test nay roi xoa - khong dung vao paper cac spec khac can.
  await page.getByLabel("Nhập từ arXiv").fill("2401.99999");
  await page.getByRole("button", { name: "Thêm" }).click();
  await expect(page).toHaveURL(/\/p\/arxiv-2401.99999$/, { timeout: 15_000 });
  await page.getByRole("button", { name: "Tùy chọn cho Paper 2401.99999" }).click();
  await page.getByRole("menuitem", { name: "Xoá bài báo" }).click();
  await page.getByRole("button", { name: "Xoá", exact: true }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3100/");
  await expect(page.getByRole("navigation", { name: "Bài báo" }).getByText("Paper 2401.99999")).toHaveCount(0);
});
