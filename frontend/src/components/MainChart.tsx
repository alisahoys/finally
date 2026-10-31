import { formatPercent, formatPrice, gainClass } from "@/data/format";
import type { ChartPoint } from "@/data/history";
import { colors } from "@/data/theme";
import type { PriceUpdate } from "@/data/types";
import { LineChart } from "./LineChart";
import { TradeBar, type PlaceTrade } from "./TradeBar";

interface MainChartProps {
  ticker: string | null;
  price?: PriceUpdate;
  points?: ChartPoint[];
  onTrade: PlaceTrade;
}

/** Large chart of the focused ticker since page load, with the trade ticket beneath. */
export function MainChart({ ticker, price, points, onTrade }: MainChartProps) {
  return (
    <section aria-label="Price chart" className="flex min-h-96 min-w-0 flex-col bg-panel lg:min-h-0">
      <header className="flex shrink-0 items-baseline gap-3 px-3 pt-2">
        <h2 className="text-2xl font-bold text-focus">{ticker ?? "--"}</h2>
        <p className="text-3xl font-light">{formatPrice(price?.price)}</p>
        <p className={`font-medium ${gainClass(price?.session_change_percent)}`}>
          {formatPercent(price?.session_change_percent)}
        </p>
        <p className="text-sm text-muted">since open at {formatPrice(price?.open_price)}</p>
      </header>
      <div className="min-h-0 flex-1 px-1 pb-1">
        <LineChart
          attribution
          points={points}
          revision={price?.timestamp}
          color={colors.focus}
          openPrice={price?.open_price}
        />
      </div>
      <TradeBar ticker={ticker} onTrade={onTrade} />
    </section>
  );
}
