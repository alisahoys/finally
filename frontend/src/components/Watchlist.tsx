import { useState, type FormEvent } from "react";
import { formatPercent, gainClass } from "@/data/format";
import type { PriceHistory } from "@/data/history";
import { colors } from "@/data/theme";
import type { PriceMap, PriceUpdate, WatchlistEntry } from "@/data/types";
import { FlashingPrice } from "./FlashingPrice";
import { LineChart } from "./LineChart";
import { Panel } from "./Panel";

interface RowProps {
  ticker: string;
  update?: PriceUpdate;
  points: PriceHistory[string] | undefined;
  focused: boolean;
  onSelect: () => void;
  onRemove: () => void;
}

function WatchlistRow({ ticker, update, points, focused, onSelect, onRemove }: RowProps) {
  const change = update?.session_change_percent;
  return (
    <li
      className={`group relative flex items-center border-l-2 hover:bg-raised ${
        focused ? "border-focus bg-raised" : "border-transparent"
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={focused}
        className="grid h-9 min-w-0 flex-1 grid-cols-[3.25rem_minmax(0,1fr)_4.75rem_3.75rem] items-center gap-1 pr-6 pl-2.5 text-left"
      >
        <span className={`font-semibold ${focused ? "text-focus" : ""}`}>{ticker}</span>
        <span className="pointer-events-none h-6">
          <LineChart
            compact
            points={points}
            revision={update?.timestamp}
            color={(change ?? 0) < 0 ? colors.loss : colors.gain}
          />
        </span>
        <span className="text-right">{update ? <FlashingPrice update={update} /> : "--"}</span>
        <span className={`text-right text-sm ${gainClass(change)}`}>{formatPercent(change)}</span>
      </button>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${ticker} from watchlist`}
        className="absolute right-1 size-5 rounded-sm text-muted opacity-0 group-hover:opacity-100 hover:text-ink focus-visible:opacity-100"
      >
        &times;
      </button>
    </li>
  );
}

function AddTickerForm({ onAdd }: { onAdd: (ticker: string) => Promise<void> }) {
  const [ticker, setTicker] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await onAdd(ticker.trim());
      setTicker("");
    } catch (failure) {
      setError((failure as Error).message);
    }
  }

  return (
    <form onSubmit={submit} className="shrink-0 border-t border-line p-2">
      <div className="flex gap-2">
        <input
          aria-label="Ticker to add"
          placeholder="Add a ticker"
          value={ticker}
          onChange={(event) => setTicker(event.target.value.toUpperCase())}
          required
          maxLength={5}
          className="field min-w-0 flex-1"
        />
        <button type="submit" className="btn-submit">
          Add
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-1 text-sm text-loss">
          {error}
        </p>
      )}
    </form>
  );
}

interface WatchlistProps {
  entries: WatchlistEntry[];
  prices: PriceMap;
  history: PriceHistory;
  focus: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => void;
}

/** List watched tickers with live prices; selecting one focuses the terminal on it. */
export function Watchlist(props: WatchlistProps) {
  const { entries, prices, history, focus, onSelect, onAdd, onRemove } = props;
  return (
    <Panel title="Watchlist" className="max-lg:h-[30rem]">
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {entries.map(({ ticker }) => (
          <WatchlistRow
            key={ticker}
            ticker={ticker}
            update={prices[ticker]}
            points={history[ticker]}
            focused={ticker === focus}
            onSelect={() => onSelect(ticker)}
            onRemove={() => onRemove(ticker)}
          />
        ))}
      </ul>
      <AddTickerForm onAdd={onAdd} />
    </Panel>
  );
}
