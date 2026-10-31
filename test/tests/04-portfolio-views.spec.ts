import { expect, test } from "@playwright/test";
import { hasPaintedCanvas, openTerminal, panel, placeOrder, positionRow } from "./helpers";

/** Read a tile's P&L text and fill color at the same instant. */
const readTile = (page: import("@playwright/test").Page, ticker: string) =>
  page.getByTestId(`tile-${ticker}`).evaluate((tile) => {
    const percent = parseFloat(tile.querySelectorAll("span")[1].textContent!);
    const probe = document.createElement("canvas").getContext("2d", { willReadFrequently: true })!;
    probe.fillStyle = getComputedStyle(tile).backgroundColor;
    probe.fillRect(0, 0, 1, 1);
    const [red, green] = probe.getImageData(0, 0, 1, 1).data;
    return { percent, red, green };
  });

test("heatmap colors tiles by P&L and sizes them by weight", async ({ page }) => {
  await openTerminal(page);
  await placeOrder(page, "META", 4, "Buy");
  await expect(positionRow(page, "META")).toBeVisible();
  await placeOrder(page, "AMZN", 1, "Buy");
  await expect(positionRow(page, "AMZN")).toBeVisible();

  const meta = page.getByTestId("tile-META");
  const amzn = page.getByTestId("tile-AMZN");
  const area = async (tile: typeof meta) => {
    const box = (await tile.boundingBox())!;
    return box.width * box.height;
  };
  expect(await area(meta)).toBeGreaterThan(await area(amzn));

  await expect
    .poll(async () => {
      const { percent, red, green } = await readTile(page, "META");
      return percent !== 0 && percent > 0 === green > red;
    }, { timeout: 30_000 })
    .toBe(true);
});

test("P&L chart draws the recorded snapshots", async ({ page, request }) => {
  await openTerminal(page);
  const snapshots = await (await request.get("/api/portfolio/history")).json();
  expect(snapshots.length).toBeGreaterThan(1);
  const chart = panel(page, "Portfolio value");
  await expect(chart.getByText("The value line starts")).toHaveCount(0);
  await expect.poll(() => hasPaintedCanvas(chart)).toBe(true);
});

test("positions table shows every column", async ({ page }) => {
  await openTerminal(page);
  const cells = positionRow(page, "META").getByRole("cell");
  await expect(cells.nth(0)).toHaveText("4");
  await expect(cells.nth(1)).toHaveText(/\d+\.\d{2}/);
  await expect(cells.nth(2)).toHaveText(/\d+\.\d{2}/);
  await expect(cells.nth(3)).toHaveText(/[+-]\$\d/);
  await expect(cells.nth(4)).toHaveText(/[+-]\d+\.\d{2}%/);
});
