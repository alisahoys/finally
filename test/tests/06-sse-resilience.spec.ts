import { connect, createServer, type Socket } from "node:net";
import { expect, test } from "@playwright/test";
import { openTerminal, watchlistRow } from "./helpers";

const PROXY_PORT = 9000;
const backend = new URL(process.env.BASE_URL ?? "http://localhost:8000");

test.use({ baseURL: `http://127.0.0.1:${PROXY_PORT}` });

/** TCP proxy to the app: the browser's offline mode leaves open SSE streams alone. */
function createProxy() {
  const sockets = new Set<Socket>();
  const server = createServer((client) => {
    const upstream = connect(Number(backend.port), backend.hostname);
    for (const socket of [client, upstream]) {
      sockets.add(socket);
      socket.on("error", () => {});
      socket.on("close", () => {
        sockets.delete(socket);
        client.destroy();
        upstream.destroy();
      });
    }
    client.pipe(upstream).pipe(client);
  });
  return {
    start: () => new Promise<void>((resolve) => server.listen(PROXY_PORT, "127.0.0.1", resolve)),
    stop: () =>
      new Promise<void>((resolve) => {
        server.close(() => resolve());
        for (const socket of sockets) socket.destroy();
      }),
  };
}

test("reconnects after the connection drops and resumes prices", async ({ page }) => {
  const proxy = createProxy();
  await proxy.start();
  await openTerminal(page);
  const status = page.locator("header").getByRole("status");

  await proxy.stop();
  await expect(status).toHaveText("Reconnecting");

  await proxy.start();
  await expect(status).toHaveText("Live", { timeout: 15_000 });

  const price = watchlistRow(page, "AAPL").locator("span.rounded-sm");
  const first = await price.textContent();
  await expect.poll(() => price.textContent(), { timeout: 15_000 }).not.toBe(first);
  await proxy.stop();
});
