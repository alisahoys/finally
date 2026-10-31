import { expect, test } from "@playwright/test";
import { getPortfolio, headerFigure, openTerminal, panel, placeOrder, positionRow, watchlistRow } from "./helpers";

test.beforeEach(({ page }) => openTerminal(page));

test("buying reduces cash and opens a position", async ({ page, request }) => {
  const cashBefore = await headerFigure(page, "Cash");
  await placeOrder(page, "JPM", 2, "Buy");

  const ticket = panel(page, "Price chart");
  await expect(ticket.getByRole("status")).toHaveText(/Bought 2 JPM at \$/);
  await expect(positionRow(page, "JPM")).toBeVisible();
  await expect(page.getByTestId("tile-JPM")).toBeVisible();

  const { positions } = await getPortfolio(request);
  const jpm = positions.find((position: { ticker: string }) => position.ticker === "JPM");
  expect(jpm.quantity).toBe(2);
  await expect.poll(() => headerFigure(page, "Cash")).toBeCloseTo(cashBefore - 2 * jpm.avg_cost, 1);
});

test("selling raises cash; selling everything closes the position", async ({ page }) => {
  await placeOrder(page, "V", 3, "Buy");
  await expect(positionRow(page, "V")).toBeVisible();
  const cashAfterBuy = await headerFigure(page, "Cash");

  await placeOrder(page, "V", 1, "Sell");
  const ticket = panel(page, "Price chart");
  await expect(ticket.getByRole("status")).toHaveText(/Sold 1 V at \$/);
  await expect(positionRow(page, "V").getByRole("cell").first()).toHaveText("2");
  await expect.poll(() => headerFigure(page, "Cash")).toBeGreaterThan(cashAfterBuy);

  await placeOrder(page, "V", 2, "Sell");
  await expect(ticket.getByRole("status")).toHaveText(/Sold 2 V at \$/);
  await expect(positionRow(page, "V")).toHaveCount(0);
  await expect(page.getByTestId("tile-V")).toHaveCount(0);
});

test("rejects orders it cannot fill and leaves cash untouched", async ({ page }) => {
  const cashBefore = await headerFigure(page, "Cash");
  const status = panel(page, "Price chart").getByRole("status");

  await placeOrder(page, "AAPL", 100000, "Buy");
  await expect(status).toHaveText(/insufficient cash/i);

  await placeOrder(page, "NFLX", 5, "Sell");
  await expect(status).toHaveText(/insufficient shares/i);

  expect(await headerFigure(page, "Cash")).toBe(cashBefore);
});

test("buying a ticker outside the watchlist tracks and values it", async ({ page }) => {
  await placeOrder(page, "SHOP", 1, "Buy");
  await expect(positionRow(page, "SHOP").getByRole("cell").nth(2)).toHaveText(/\d+\.\d{2}/);
  await expect(watchlistRow(page, "SHOP")).toHaveCount(0);

  await placeOrder(page, "SHOP", 1, "Sell");
  await expect(positionRow(page, "SHOP")).toHaveCount(0);
});

test("removing a held ticker from the watchlist keeps the position priced", async ({ page }) => {
  await placeOrder(page, "NFLX", 1, "Buy");
  await expect(positionRow(page, "NFLX")).toBeVisible();

  await watchlistRow(page, "NFLX").hover();
  await page.getByRole("button", { name: "Remove NFLX from watchlist" }).click();
  await expect(watchlistRow(page, "NFLX")).toHaveCount(0);

  await page.reload();
  await expect(positionRow(page, "NFLX").getByRole("cell").nth(2)).toHaveText(/\d+\.\d{2}/);
});
