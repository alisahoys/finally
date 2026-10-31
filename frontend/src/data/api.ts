import type { ChatReply, Portfolio, Side, Snapshot, TradeResult, WatchlistEntry } from "./types";

/** Call the backend and return its JSON, raising its `detail` message on failure. */
async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.ok) return response.json();
  const { detail } = await response.json();
  throw new Error(typeof detail === "string" ? detail : "Check your entry and try again.");
}

export const api = {
  portfolio: () => request<Portfolio>("/portfolio"),
  history: () => request<Snapshot[]>("/portfolio/history"),
  trade: (ticker: string, quantity: number, side: Side) =>
    request<TradeResult>("/portfolio/trade", "POST", { ticker, quantity, side }),
  watchlist: () => request<WatchlistEntry[]>("/watchlist"),
  addTicker: (ticker: string) => request<WatchlistEntry[]>("/watchlist", "POST", { ticker }),
  removeTicker: (ticker: string) => request<WatchlistEntry[]>(`/watchlist/${ticker}`, "DELETE"),
  chat: (message: string) => request<ChatReply>("/chat", "POST", { message }),
};
