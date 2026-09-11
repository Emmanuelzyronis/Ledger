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

const OUTCOMES = [
  "MATCHED",
  "MISMATCHED",
  "UNMATCHED_A",
  "UNMATCHED_B",
  "AMBIGUOUS",
  "DUPLICATE",
  "INVALID",
] as const;

const fixtures: Fixtures = JSON.parse(
  readFileSync(path.join(process.cwd(), "e2e", ".fixtures.json"), "utf8"),
) as Fixtures;

/** The bordered panel whose heading names the operation group. */
function panel(page: Page, title: string) {
  return page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: new RegExp(title) }) });
}

/** A SummaryBand value by its exact label. */
function stat(page: Page, label: string) {
  return page
    .locator("dl > div")
    .filter({ has: page.getByText(label, { exact: true }) })
    .locator("dd")
    .first();
}

test("the ingest screen writes through the service and reads the counters back", async ({
  page,
}) => {
  await page.goto("/ingest");

  const createBatch = panel(page, "Create batch");
  await createBatch.getByLabel("source_id").fill("source-a");
  await createBatch.getByLabel("external_batch_id").fill("E2E-BATCH-1");
  await createBatch.getByLabel("schema_version").fill("source_a.v1");
  await createBatch.getByRole("button", { name: "Create batch" }).click();

  const openBatch = page.getByRole("link", { name: "Show its counters" });
  await expect(openBatch).toBeVisible();
  const href = await openBatch.getAttribute("href");
  const batchId = decodeURIComponent(
    new URLSearchParams(href?.split("?")[1] ?? "").get("batch_id") ?? "",
  );
  expect(batchId).not.toBe("");

  await openBatch.click();
  await expect(page).toHaveURL(new RegExp(`batch_id=${encodeURIComponent(batchId)}`));
  await expect(stat(page, "Records received")).toHaveText("0");

  const ingest = panel(page, "Ingest record");
  await ingest.getByLabel("batch_id").fill(batchId);
  await ingest.getByLabel("payload (source-native JSON)").fill(
    JSON.stringify({
      record_id: "E2E-1",
      occurred_at: "2026-09-11",
      amount: "100.00",
      currency: "USD",
      direction: "CREDIT",
      transaction_reference: "E2E-REF-1",
    }),
  );
  await ingest.getByLabel("idempotency_key (optional)").fill("e2e-1");
  await ingest.getByRole("button", { name: "Ingest record" }).click();

  await expect(ingest.getByText("ACCEPTED")).toBeVisible();
  await expect(stat(page, "Records received")).toHaveText("1");
});

test("reconciliation renders the seven outcomes and the seeded counts", async ({ page }) => {
  await page.goto("/reconciliation");

  await expect(stat(page, "Reconciliation decisions")).toHaveText(
    String(fixtures.report.reconciliation_count),
  );
  await expect(stat(page, "Current versions")).toHaveText(
    String(fixtures.report.current_reconciliation_count),
  );
  await expect(stat(page, "Matched")).toHaveText(String(fixtures.report.outcomes.MATCHED));
  await expect(stat(page, "Ambiguous")).toHaveText(String(fixtures.report.outcomes.AMBIGUOUS));
  await expect(stat(page, "Open discrepancies")).toHaveText(
    String(fixtures.report.discrepancy_count),
  );

  for (const outcome of OUTCOMES) {
    await expect(
      page.getByRole("row").filter({ hasText: outcome }).first(),
      `${outcome} must be rendered`,
    ).toBeVisible();
  }
});

test("the discrepancy queue lists the seeded discrepancies and opens one", async ({ page }) => {
  const target = fixtures.resolution_target;
  await page.goto("/discrepancies");

  await expect(stat(page, "Discrepancies in scope")).toHaveText(
    String(fixtures.discrepancies.length),
  );
  await page.getByRole("link", { name: target.discrepancy_id }).click();

  await expect(
    page.getByRole("heading", { name: `Discrepancy ${target.discrepancy_id}` }),
  ).toBeVisible();
  await expect(page.getByText(target.reason).first()).toBeVisible();
  await expect(
    panel(page, "Reconciliation evidence").getByText(target.outcome).first(),
  ).toBeVisible();
  await expect(
    page
      .locator("section")
      .filter({ hasText: "Audit trail" })
      .getByRole("row")
      .filter({ hasText: "DISCREPANCY" })
      .first(),
  ).toBeVisible();
});

test("resolving through the UI records a new version and keeps the superseded one", async ({
  page,
}) => {
  const target = fixtures.resolution_target;
  await page.goto(`/discrepancies/${encodeURIComponent(target.discrepancy_id)}`);

  const resolution = panel(page, "Resolution action");
  await resolution
    .getByLabel("Reason (required, recorded immutably)")
    .fill("E2E: operator confirmed the pairing from the settlement receipt.");
  await resolution.getByRole("button", { name: "Record resolution" }).click();

  // The action's own ResolutionResult.
  await expect(resolution.getByText("v2")).toBeVisible();
  await expect(resolution.getByText(target.reconciliation_id)).toBeVisible();

  // Persisted lineage: reload and the supersession survives.
  await page.reload();
  const lineage = page.locator("section").filter({ hasText: "Resolution result" });
  await expect(lineage.getByText("v2")).toBeVisible();
  await expect(lineage.getByText(target.reconciliation_id).first()).toBeVisible();

  // The superseded decision is still retrievable at its original version.
  await page.goto(`/reconciliation?batch_id=${encodeURIComponent(target.batch_id)}`);
  await expect(page.getByRole("cell", { name: target.reconciliation_id }).first()).toBeVisible();
});
