import { describe, expect, it } from "vitest";
import { revaluePortfolio } from "./portfolio";
import type { Portfolio, PriceMap, PriceUpdate } from "./types";

const portfolio: Portfolio = {
  cash_balance: 8000,
  total_value: 10000,
  unrealized_pnl: 0,
  positions: [
    {
      ticker: "AAPL",
      quantity: 10,
      avg_cost: 200,
      current_price: 200,
      market_value: 2000,
      unrealized_pnl: 0,
      pnl_percent: 0,
    },
  ],
};

const priced = (price: number): PriceMap => ({ AAPL: { price } as PriceUpdate });

describe("revaluePortfolio", () => {
  it("marks positions to the streamed price", () => {
    const result = revaluePortfolio(portfolio, priced(210));
    expect(result.positions[0]).toMatchObject({
      current_price: 210,
      market_value: 2100,
      unrealized_pnl: 100,
      pnl_percent: 5,
    });
    expect(result.total_value).toBe(10100);
    expect(result.unrealized_pnl).toBe(100);
  });

  it("reports a loss when the price falls", () => {
    const result = revaluePortfolio(portfolio, priced(190));
    expect(result.positions[0].unrealized_pnl).toBe(-100);
    expect(result.positions[0].pnl_percent).toBe(-5);
    expect(result.total_value).toBe(9900);
  });

  it("keeps the last known price when the stream has none", () => {
    const result = revaluePortfolio(portfolio, {});
    expect(result.positions[0].current_price).toBe(200);
    expect(result.total_value).toBe(10000);
  });

  it("values an unpriced position at average cost", () => {
    const unpriced = { ...portfolio.positions[0], current_price: null };
    const result = revaluePortfolio({ ...portfolio, positions: [unpriced] }, {});
    expect(result.positions[0].current_price).toBeNull();
    expect(result.positions[0].market_value).toBe(2000);
    expect(result.positions[0].unrealized_pnl).toBe(0);
  });

  it("returns cash alone when there are no positions", () => {
    const result = revaluePortfolio({ ...portfolio, positions: [] }, {});
    expect(result.total_value).toBe(8000);
    expect(result.unrealized_pnl).toBe(0);
  });
});
