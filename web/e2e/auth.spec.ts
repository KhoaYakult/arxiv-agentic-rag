import { expect, test } from "@playwright/test";
import { appAlert, login } from "./helpers";

test("unauthenticated page redirects to login with next, wrong then right password", async ({ page }) => {
  await page.goto("/p/arxiv-1706.03762");
  await expect(page).toHaveURL(/\/login\?next=%2Fp%2Farxiv-1706.03762/);
  await page.getByPlaceholder("Mật khẩu").fill("nope");
  await page.getByRole("button", { name: "Vào" }).click();
  await expect(appAlert(page)).toHaveText("Sai mật khẩu, thử lại.");
  await page.getByPlaceholder("Mật khẩu").fill("test-pass");
  await page.getByRole("button", { name: "Vào" }).click();
  await expect(page).toHaveURL(/\/p\/arxiv-1706.03762$/);
});

test("open redirect in next is neutralised", async ({ page }) => {
  await login(page, "//evil.com");
  await expect(page).toHaveURL("http://127.0.0.1:3100/");
});

test("API without session is 401 JSON", async ({ request }) => {
  const r = await request.get("/api/papers");
  expect(r.status()).toBe(401);
  expect((await r.json()).error.code).toBe("unauthorized");
});
