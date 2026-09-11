import { defineConfig } from "@playwright/test";

/**
 * End-to-end configuration. `e2e/global-setup.ts` seeds a real SQLite database
 * with the Layer 15 fixtures and starts both the LEDGER service and this
 * dashboard, so the suite drives the real `/v1` contract end to end.
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3011",
    trace: "retain-on-failure",
  },
});
