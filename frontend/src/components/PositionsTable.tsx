import { formatPercent, formatPrice, formatShares, formatSignedMoney, gainClass } from "@/data/format";
import type { Position } from "@/data/types";
import { Panel } from "./Panel";

const COLUMNS = ["Qty", "Avg cost", "Price", "P&L", "Change"];

interface RowProps {
  position: Position;
  focused: boolean;
  onSelect: () => void;
}

function PositionRow({ position, focused, onSelect }: RowProps) {
  const { ticker, quantity, avg_cost, current_price, unrealized_pnl, pnl_percent } = position;
  const tone = gainClass(unrealized_pnl);
  return (
    <tr className={focused ? "bg-raised" : "hover:bg-raised"}>
      <th
        scope="row"
        className={`border-l-2 pl-2.5 text-left font-semibold ${
          focused ? "border-focus" : "border-transparent"
        }`}
      >
        <button
          type="button"
          onClick={onSelect}
          className={`py-1 font-semibold ${focused ? "text-focus" : ""}`}
        >
          {ticker}
        </button>
      </th>
      <td className="px-2 text-right">{formatShares(quantity)}</td>
      <td className="px-2 text-right">{formatPrice(avg_cost)}</td>
      <td className="px-2 text-right">{formatPrice(current_price)}</td>
      <td className={`px-2 text-right ${tone}`}>{formatSignedMoney(unrealized_pnl)}</td>
      <td className={`px-3 text-right ${tone}`}>{formatPercent(pnl_percent)}</td>
    </tr>
  );
}

interface PositionsTableProps {
  positions: Position[];
  focus: string | null;
  onSelect: (ticker: string) => void;
}

/** Table of open positions, marked to the latest price. */
export function PositionsTable({ positions, focus, onSelect }: PositionsTableProps) {
  return (
    <Panel title="Positions" className="max-lg:min-h-48">
      {positions.length === 0 ? (
        <p className="m-auto max-w-56 text-center text-sm text-muted">
          No open positions. Buy shares with the ticket above or ask FinAlly.
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full text-sm whitespace-nowrap">
            <thead className="sticky top-0 bg-panel text-muted">
              <tr>
                <th scope="col" className="pl-3 text-left font-medium">
                  Ticker
                </th>
                {COLUMNS.map((column) => (
                  <th key={column} scope="col" className="px-2 text-right font-medium last:pr-3">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <PositionRow
                  key={position.ticker}
                  position={position}
                  focused={position.ticker === focus}
                  onSelect={() => onSelect(position.ticker)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
