import { useState, type FormEvent } from "react";
import { formatPrice, formatShares } from "@/data/format";
import type { Side, Trade } from "@/data/types";

export type PlaceTrade = (ticker: string, quantity: number, side: Side) => Promise<Trade>;

const describeFill = ({ side, quantity, ticker, price }: Trade) =>
  `${side === "buy" ? "Bought" : "Sold"} ${formatShares(quantity)} ${ticker} at $${formatPrice(price)}`;

interface TradeBarProps {
  ticker: string | null;
  onTrade: PlaceTrade;
}

/** Market order ticket; the ticker field follows the focused ticker until edited. */
export function TradeBar({ ticker, onTrade }: TradeBarProps) {
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement;
    const form = new FormData(event.currentTarget);
    try {
      const trade = await onTrade(
        String(form.get("ticker")).trim(),
        Number(form.get("quantity")),
        submitter.value as Side,
      );
      setResult({ text: describeFill(trade), failed: false });
    } catch (failure) {
      setResult({ text: (failure as Error).message, failed: true });
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2 border-t border-line p-2">
      <input
        key={ticker}
        name="ticker"
        aria-label="Ticker"
        placeholder="Ticker"
        defaultValue={ticker ?? ""}
        required
        maxLength={5}
        className="field w-20 uppercase"
      />
      <input
        name="quantity"
        aria-label="Quantity"
        placeholder="Quantity"
        type="number"
        min="0"
        step="any"
        required
        className="field w-24"
      />
      <button type="submit" value="buy" className="btn-submit w-16">
        Buy
      </button>
      <button type="submit" value="sell" className="btn-outline w-16">
        Sell
      </button>
      {result && (
        <p role="status" className={`ml-1 text-sm ${result.failed ? "text-loss" : "text-ink"}`}>
          {result.text}
        </p>
      )}
    </form>
  );
}
