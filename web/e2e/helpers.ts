import { expect, type Page } from "@playwright/test";

export async function login(page: Page, next = "/") {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByPlaceholder("Mật khẩu").fill("test-pass");
  await page.getByRole("button", { name: "Vào" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

// Next.js chen san 1 role=alert (route announcer) vao moi trang -> loai no ra de strict mode khong bao trung.
export const appAlert = (page: Page) => page.locator('[role="alert"]:not(#__next-route-announcer__)');
