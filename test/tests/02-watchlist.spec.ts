import { expect, test } from "@playwright/test";
import { openTerminal, panel, watchlistRow } from "./helpers";

test.beforeEach(({ page }) => openTerminal(page));

test("adds a ticker, which starts streaming, and removes it", async ({ page }) => {
  const watchlist = panel(page, "Watchlist");
  await watchlist.getByLabel("Ticker to add").fill("pypl");
  await watchlist.getByRole("button", { name: "Add", exact: true }).click();

  const row = watchlistRow(page, "PYPL");
  await expect(row).toBeVisible();
  await expect(row.locator("span.rounded-sm")).toHaveText(/\d+\.\d{2}/);

  await page.reload();
  await expect(watchlistRow(page, "PYPL")).toBeVisible();

  await row.hover();
  await page.getByRole("button", { name: "Remove PYPL from watchlist" }).click();
  await expect(row).toHaveCount(0);
  await page.reload();
  await expect(watchlistRow(page, "AAPL")).toBeVisible();
  await expect(row).toHaveCount(0);
});

test("rejects a duplicate and an invalid ticker", async ({ page }) => {
  const watchlist = panel(page, "Watchlist");
  const add = watchlist.getByRole("button", { name: "Add", exact: true });

  await watchlist.getByLabel("Ticker to add").fill("AAPL");
  await add.click();
  await expect(watchlist.getByRole("alert")).toHaveText("AAPL is already on the watchlist");

  await watchlist.getByLabel("Ticker to add").fill("A1");
  await add.click();
  await expect(watchlist.getByRole("alert")).toHaveText("Invalid ticker: A1");
});
