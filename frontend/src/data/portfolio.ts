import type { Portfolio, Position, PriceMap } from "./types";

function revaluePosition(position: Position, prices: PriceMap): Position {
  const current_price = prices[position.ticker]?.price ?? position.current_price;
  const mark = current_price ?? position.avg_cost;
  const cost = position.quantity * position.avg_cost;
  const market_value = position.quantity * mark;
  const unrealized_pnl = market_value - cost;
  return {
    ...position,
    current_price,
    market_value,
    unrealized_pnl,
    pnl_percent: (unrealized_pnl / cost) * 100,
  };
}

/** Mark a portfolio to the latest streamed prices, so totals move between fetches. */
export function revaluePortfolio(portfolio: Portfolio, prices: PriceMap): Portfolio {
  const positions = portfolio.positions.map((position) => revaluePosition(position, prices));
  const sum = (pick: (position: Position) => number) =>
    positions.reduce((total, position) => total + pick(position), 0);
  return {
    ...portfolio,
    positions,
    total_value: portfolio.cash_balance + sum((position) => position.market_value),
    unrealized_pnl: sum((position) => position.unrealized_pnl),
  };
}
