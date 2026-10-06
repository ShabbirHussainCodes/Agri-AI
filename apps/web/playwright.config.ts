import { defineConfig, devices } from "@playwright/test";

// The tests run the real production build against a STUBBED API and a stubbed Supabase session
// (tests/helpers.ts), so they need no database, no LLM quota and no network.
const PORT = 3100;
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    ...devices["Pixel 5"],
    launchOptions: { executablePath },
  },
  webServer: {
    command: `npm run build && npm run start -- -p ${PORT}`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
    env: {
      NEXT_PUBLIC_API_BASE_URL: "http://api.test",
      NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:54321",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-anon-key",
      NEXT_PUBLIC_SEND_UI_LANGUAGE: "true",
      NEXT_TELEMETRY_DISABLED: "1",
    },
  },
});
