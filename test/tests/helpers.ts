import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";

export const DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"];

export const panel = (page: Page, name: string) => page.getByRole("region", { name });

export const watchlistRow = (page: Page, ticker: string) =>
  panel(page, "Watchlist")
    .getByRole("listitem")
    .filter({ has: page.getByRole("button", { name: `Remove ${ticker} from watchlist` }) });

export const positionRow = (page: Page, ticker: string) =>
  panel(page, "Positions").getByRole("row").filter({ has: page.getByRole("button", { name: ticker, exact: true }) });

/** The value of a header figure, e.g. "Cash", parsed from "$8,095.00". */
export async function headerFigure(page: Page, label: string) {
  const text = await page.locator("header dt", { hasText: label }).locator("+ dd").textContent();
  return Number(text!.replace(/[^0-9.-]/g, ""));
}

/** Open the terminal and wait until prices stream and the account has loaded. */
export async function openTerminal(page: Page) {
  await page.goto("/");
  await expect(page.locator("header").getByRole("status")).toHaveText("Live");
  await expect(watchlistRow(page, "AAPL")).toBeVisible();
  await expect(page.locator("header dt", { hasText: "Cash" }).locator("+ dd")).not.toHaveText("--");
}

/** Submit the order ticket, filled for the given ticker and quantity. */
export async function placeOrder(page: Page, ticker: string, quantity: number, side: "Buy" | "Sell") {
  const ticket = panel(page, "Price chart");
  await ticket.getByLabel("Ticker", { exact: true }).fill(ticker);
  await ticket.getByLabel("Quantity").fill(String(quantity));
  await ticket.getByRole("button", { name: side, exact: true }).click();
}

/** True once any canvas in the locator has painted at least one pixel. */
export const hasPaintedCanvas = (scope: Locator) =>
  scope.evaluate((root) =>
    [...root.querySelectorAll("canvas")].some((canvas) => {
      const { width, height } = canvas;
      const pixels = canvas.getContext("2d")?.getImageData(0, 0, width, height).data ?? [];
      return pixels.some((value, index) => index % 4 === 3 && value > 0);
    }),
  );

export async function getPortfolio(request: APIRequestContext) {
  return (await request.get("/api/portfolio")).json();
}
