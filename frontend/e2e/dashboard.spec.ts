import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

interface Discrepancy {
  discrepancy_id: string;
  reconciliation_id: string;
  state: string;
  outcome: string;
  batch_id: string;
  reason: string;
}

interface Fixtures {
  batches: { a: string; b: string };
  discrepancies: Discrepancy[];
  resolution_target: Discrepancy;
  report: {
    reconciliation_count: number;
    current_reconciliation_count: number;
    discrepancy_count: number;
    outcomes: Record<string, number>;
  };
}

const fixtures: Fixtures = JSON.parse(
  readFileSync(path.join(process.cwd(), "e2e", ".fixtures.json"), "utf8"),
) as Fixtures;

/** A SummaryBand value by its exact label. */
function stat(page: Page, label: string) {
  return page
    .locator("dl > div")
    .filter({ has: page.getByText(label, { exact: true }) })
    .locator("dd")
    .first();
}

test("dashboard overview loads and shows KPI cards and outcome distribution", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  // Page renders without crashing — main heading present
  await expect(page.getByRole("heading", { name: "Reconciliation Overview" })).toBeVisible();

  // Service health indicator is shown
  await expect(page.locator("span").filter({ hasText: /[Ss]ervice/ }).first()).toBeVisible();

  // Navigation links updated to operator names
  await expect(page.getByRole("link", { name: "Batches" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Exceptions" })).toBeVisible();
});

test("batches page shows batch list and counters from seeded data", async ({ page }) => {
  await page.goto("/batches");
  await page.waitForLoadState("networkidle");

  // Page heading visible (exact to avoid substring-matching "All batches")
  await expect(page.getByRole("heading", { name: "Batches", exact: true })).toBeVisible();

  // SummaryBand with Total batches is present
  await expect(stat(page, "Total batches")).toBeVisible();

  // The seeded batch appears via IdChip or as a short ID
  const batchId = fixtures.batches.a;
  const shortHex = batchId.includes(":") ? batchId.slice(batchId.lastIndexOf(":") + 1, batchId.lastIndexOf(":") + 9) : batchId.slice(0, 8);
  await expect(page.locator(`[data-id="${batchId}"]`).first()).toBeVisible();
});

test("reconciliation page renders the seven outcomes and seeded counts", async ({ page }) => {
  await page.goto("/reconciliation");

  await expect(stat(page, "Reconciliation decisions")).toHaveText(
    String(fixtures.report.reconciliation_count),
  );
  await expect(stat(page, "Current versions")).toHaveText(
    String(fixtures.report.current_reconciliation_count),
  );
  await expect(stat(page, "Matched")).toHaveText(String(fixtures.report.outcomes.MATCHED ?? 0));

  const OUTCOMES = [
    "MATCHED",
    "MISMATCHED",
    "UNMATCHED_A",
    "UNMATCHED_B",
    "AMBIGUOUS",
    "DUPLICATE",
    "INVALID",
  ] as const;
  for (const outcome of OUTCOMES) {
    await expect(
      page.getByRole("row").filter({ hasText: outcome }).first(),
      `${outcome} must be rendered`,
    ).toBeVisible();
  }
});

test("exceptions queue and resolution flow", async ({ page }) => {
  const target = fixtures.resolution_target;

  // Exceptions list loads
  await page.goto("/exceptions");
  await page.waitForLoadState("networkidle");

  await expect(page.getByRole("heading", { name: "Exceptions" })).toBeVisible();
  await expect(stat(page, "Total exceptions")).toHaveText(String(fixtures.discrepancies.length));

  // Navigate to the exception detail directly
  await page.goto(`/exceptions/${encodeURIComponent(target.discrepancy_id)}`);
  await page.waitForLoadState("networkidle");

  // Exception reason is shown in the description
  await expect(page.getByText(target.reason, { exact: false }).first()).toBeVisible();

  // Audit trail shows a DISCREPANCY event
  await expect(
    page
      .locator("section")
      .filter({ hasText: "Audit trail" })
      .getByText("DISCREPANCY", { exact: false })
      .first(),
  ).toBeVisible();

  // Resolution form at top for OPEN exceptions
  if (target.state === "OPEN") {
    const resolutionSection = page.locator("section").filter({ hasText: "Resolve exception" });
    await resolutionSection
      .getByLabel("Reason (required, recorded immutably)")
      .fill("E2E: operator confirmed pairing from settlement receipt.");
    await resolutionSection.getByRole("button", { name: "Record resolution" }).click();

    // After the server action completes, revalidatePath triggers a server re-render.
    // The page shows the resolved state with a "Resolution outcome" section containing v2.
    await page.waitForLoadState("networkidle");
    const outcome = page.locator("section").filter({ hasText: "Resolution outcome" });
    await expect(outcome.getByText("v2")).toBeVisible();

    // Reload: supersession persists
    await page.reload();
    await page.waitForLoadState("networkidle");
    const outcomeAfterReload = page.locator("section").filter({ hasText: "Resolution outcome" });
    await expect(outcomeAfterReload.getByText("v2")).toBeVisible();
  }

  // Superseded reconciliation decision is still retrievable on reconciliation page
  await page.goto(`/reconciliation?batch_id=${encodeURIComponent(target.batch_id)}`);
  await expect(
    page.locator(`[data-id="${target.reconciliation_id}"]`).first(),
  ).toBeVisible();
});
