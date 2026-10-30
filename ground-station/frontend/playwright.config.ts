import { defineConfig, devices } from "@playwright/test";

// End-to-end tests boot a throw-away backend (SQLite in a temp dir) and the Vite
// dev server. Test tokens below exist only for this run.
const E2E_TOKEN = "e2e-operator-token";
const E2E_ADMIN = "e2e-admin-token";
const dataDir = process.env.KS_E2E_DATA ?? "/tmp/khmersat-e2e";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1600, height: 1000 },
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 1000 } } }],
  webServer: [
    {
      command: `rm -rf ${dataDir} && uv run python -m uvicorn app.main:app --app-dir ground-station/backend --host 127.0.0.1 --port 8000`,
      cwd: "../..",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        OPERATOR_TOKEN: E2E_TOKEN,
        ADMIN_TOKEN: E2E_ADMIN,
        COMMAND_HMAC_KEY: "ab".repeat(32),
        DATABASE_URL: `sqlite:///${dataDir}/ground.db`,
        LOCAL_OBJECT_DIR: `${dataDir}/objects`,
        ONBOARD_DATA_DIR: `${dataDir}/onboard`,
        OBJECT_STORE: "local",
        MQTT_ENABLED: "false",
        SIM_TIME_SCALE: "2",
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
