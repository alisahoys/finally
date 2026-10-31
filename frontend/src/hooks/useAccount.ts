import { useCallback, useEffect, useState } from "react";
import { api } from "@/data/api";
import type { Portfolio, Side, Snapshot, WatchlistEntry } from "@/data/types";

const HISTORY_REFRESH_MS = 30_000;

/** Hold the server-side account state; `connected` triggers each reload. */
export function useAccount(connected: boolean) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);

  const refreshHistory = useCallback(async () => setSnapshots(await api.history()), []);

  const reload = useCallback(async () => {
    const [nextPortfolio, nextWatchlist] = await Promise.all([api.portfolio(), api.watchlist()]);
    setPortfolio(nextPortfolio);
    setWatchlist(nextWatchlist);
    await refreshHistory();
  }, [refreshHistory]);

  useEffect(() => {
    if (!connected) return;
    reload();
    const timer = setInterval(refreshHistory, HISTORY_REFRESH_MS);
    return () => clearInterval(timer);
  }, [connected, reload, refreshHistory]);

  const trade = useCallback(
    async (ticker: string, quantity: number, side: Side) => {
      const result = await api.trade(ticker, quantity, side);
      setPortfolio(result.portfolio);
      await refreshHistory();
      return result.trade;
    },
    [refreshHistory],
  );

  const addTicker = useCallback(async (ticker: string) => {
    setWatchlist(await api.addTicker(ticker));
  }, []);

  const removeTicker = useCallback(async (ticker: string) => {
    setWatchlist(await api.removeTicker(ticker));
  }, []);

  return { portfolio, watchlist, snapshots, reload, trade, addTicker, removeTicker };
}
