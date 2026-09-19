import { test } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const OUT = path.join(__dirname, "../.screenshots");
fs.mkdirSync(OUT, { recursive: true });

const PAGES = [
  { name: "01-overview", url: "/" },
  { name: "02-batches", url: "/batches" },
  { name: "03-reconciliation", url: "/reconciliation" },
  { name: "04-exceptions", url: "/exceptions" },
  { name: "05-reports", url: "/reports" },
];

for (const { name, url } of PAGES) {
  test(`screenshot ${name}`, async ({ page }) => {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  });
}

test("screenshot 06-exception-detail", async ({ page }) => {
  await page.goto("/exceptions");
  await page.waitForLoadState("networkidle");
  // Use the "Resolve →" or "View" action links which use the new route
  const actionLink = page.getByRole("link", { name: /Resolve|View/ }).first();
  const href = await actionLink.getAttribute("href").catch(() => null);
  if (href) {
    await page.goto(href);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: path.join(OUT, "06-exception-detail.png"), fullPage: true });
  } else {
    // Fallback: take a screenshot of the exceptions list
    await page.screenshot({ path: path.join(OUT, "06-exception-detail.png"), fullPage: true });
  }
});
