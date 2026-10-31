import { expect, test } from "@playwright/test";
import { DEFAULT_TICKERS, hasPaintedCanvas, headerFigure, openTerminal, panel, watchlistRow } from "./helpers";

test.beforeEach(({ page }) => openTerminal(page));

test("shows the default watchlist and $10k balance", async ({ page }) => {
  await expect(panel(page, "Watchlist").getByRole("listitem")).toHaveCount(DEFAULT_TICKERS.length);
  for (const ticker of DEFAULT_TICKERS) await expect(watchlistRow(page, ticker)).toBeVisible();
  expect(await headerFigure(page, "Cash")).toBe(10000);
  expect(await headerFigure(page, "Total value")).toBe(10000);
  await expect(page.getByText("No open positions.")).toBeVisible();
  await expect(panel(page, "FinAlly assistant").getByLabel("Message FinAlly")).toBeVisible();
});

test("streams prices with flashes and sparklines", async ({ page }) => {
  const row = watchlistRow(page, "AAPL");
  const price = row.locator("span.rounded-sm");
  const first = await price.textContent();
  await expect.poll(() => price.textContent(), { timeout: 15_000 }).not.toBe(first);
  await expect(panel(page, "Watchlist").locator(".flash-up, .flash-down").first()).toBeVisible();
  await expect.poll(() => hasPaintedCanvas(row)).toBe(true);
});

test("selecting a ticker focuses the main chart", async ({ page }) => {
  const chart = panel(page, "Price chart");
  await watchlistRow(page, "TSLA").getByRole("button", { name: /^TSLA/ }).click();
  await expect(chart.getByRole("heading", { name: "TSLA" })).toBeVisible();
  await expect(chart.getByLabel("Ticker", { exact: true })).toHaveValue("TSLA");
  await expect.poll(() => hasPaintedCanvas(chart)).toBe(true);
});
