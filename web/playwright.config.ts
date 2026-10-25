import { defineConfig, devices } from "@playwright/test";

const env = {
  API_BASE: "http://127.0.0.1:8799",
  APP_API_KEY: "test-key",
  ACCESS_PASSWORD: "test-pass",
  SESSION_SECRET: "e2e-only-secret-0123456789abcdef0123456789",
};

export default defineConfig({
  testDir: "e2e",
  timeout: 45_000,
  // Mock backend giu state trong bo nho (them/xoa paper) -> chay tuan tu.
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /screenshots|chat\.spec/ },
  ],
  webServer: [
    { command: "node e2e/mock-backend.mjs", port: 8799, reuseExistingServer: !process.env.CI, env },
    {
      command: "npm run build && npx next start -p 3100 -H 127.0.0.1",
      port: 3100,
      timeout: 240_000,
      reuseExistingServer: !process.env.CI,
      env,
    },
  ],
});
