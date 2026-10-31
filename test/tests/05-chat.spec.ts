import { expect, test } from "@playwright/test";
import { openTerminal, panel, positionRow, watchlistRow } from "./helpers";

test.beforeEach(({ page }) => openTerminal(page));

async function send(page: import("@playwright/test").Page, message: string) {
  const chat = panel(page, "FinAlly assistant");
  await chat.getByLabel("Message FinAlly").fill(message);
  await chat.getByRole("button", { name: "Send" }).click();
  return chat;
}

test("replies to a plain message", async ({ page }) => {
  const chat = await send(page, "How is my portfolio?");
  await expect(chat.getByText("How is my portfolio?")).toBeVisible();
  await expect(chat.getByText("Mock: I received your message.")).toBeVisible();
});

test("executes a trade inline and updates the portfolio", async ({ page }) => {
  const chat = await send(page, "buy 1 NVDA");
  await expect(chat.getByText("Mock: buying 1 NVDA.")).toBeVisible();
  await expect(chat.getByRole("listitem").filter({ hasText: /Bought 1 NVDA at \$/ })).toBeVisible();
  await expect(positionRow(page, "NVDA")).toBeVisible();
});

test("shows a failed trade inline", async ({ page }) => {
  const chat = await send(page, "sell 5000 NVDA");
  await expect(chat.getByRole("listitem").filter({ hasText: /Could not sell 5,000 NVDA/ })).toBeVisible();
});

test("adds to the watchlist", async ({ page }) => {
  const chat = await send(page, "watch DIS");
  await expect(chat.getByText("Mock: adding DIS to your watchlist.")).toBeVisible();
  await expect(chat.getByRole("listitem").filter({ hasText: "Added DIS to your watchlist" })).toBeVisible();
  await expect(watchlistRow(page, "DIS")).toBeVisible();
});

test("starts empty after a reload", async ({ page }) => {
  await send(page, "hello");
  await expect(page.getByText("Mock: I received your message.")).toBeVisible();
  await openTerminal(page);
  await expect(page.getByText("Mock: I received your message.")).toHaveCount(0);
});
