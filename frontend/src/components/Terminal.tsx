"use client";

import { useMemo, useState } from "react";
import { revaluePortfolio } from "@/data/portfolio";
import { useAccount } from "@/hooks/useAccount";
import { usePriceStream } from "@/hooks/usePriceStream";
import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { Heatmap } from "./Heatmap";
import { MainChart } from "./MainChart";
import { PositionsTable } from "./PositionsTable";
import { ValueChart } from "./ValueChart";
import { Watchlist } from "./Watchlist";

/** The workstation: owns the focused ticker and wires live data to every panel. */
export function Terminal() {
  const { prices, status, history } = usePriceStream();
  const account = useAccount(status === "connected");
  const [selected, setSelected] = useState<string | null>(null);

  const focus = selected ?? account.watchlist[0]?.ticker ?? null;
  const portfolio = useMemo(
    () => account.portfolio && revaluePortfolio(account.portfolio, prices),
    [account.portfolio, prices],
  );
  const positions = portfolio?.positions ?? [];

  async function removeTicker(ticker: string) {
    await account.removeTicker(ticker);
    if (ticker === selected) setSelected(null);
  }

  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh">
      <Header portfolio={portfolio} status={status} />
      <main className="grid flex-1 grid-cols-1 gap-px border-t border-line bg-line lg:min-h-0 lg:grid-cols-[19rem_minmax(0,1fr)_23rem] lg:grid-rows-[minmax(0,1fr)_18rem]">
        <Watchlist
          entries={account.watchlist}
          prices={prices}
          history={history}
          focus={focus}
          onSelect={setSelected}
          onAdd={account.addTicker}
          onRemove={removeTicker}
        />
        <MainChart
          ticker={focus}
          price={focus ? prices[focus] : undefined}
          points={focus ? history[focus] : undefined}
          onTrade={account.trade}
        />
        <ChatPanel onActions={account.reload} />
        <div className="grid grid-cols-1 gap-px md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.35fr)] lg:col-span-2 lg:row-start-2">
          <Heatmap positions={positions} focus={focus} onSelect={setSelected} />
          <ValueChart snapshots={account.snapshots} />
          <PositionsTable positions={positions} focus={focus} onSelect={setSelected} />
        </div>
      </main>
    </div>
  );
}
