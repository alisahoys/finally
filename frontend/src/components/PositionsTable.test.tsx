import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { revaluePortfolio } from "@/data/portfolio";
import type { Portfolio, PriceUpdate } from "@/data/types";
import { PositionsTable } from "./PositionsTable";

const portfolio: Portfolio = {
  cash_balance: 0,
  total_value: 0,
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

describe("PositionsTable", () => {
  it("shows a position marked to the live price", () => {
    const prices = { AAPL: { price: 190 } as PriceUpdate };
    const { positions } = revaluePortfolio(portfolio, prices);
    render(<PositionsTable positions={positions} focus={null} onSelect={vi.fn()} />);
    const row = screen.getByRole("row", { name: /AAPL/ });
    expect(within(row).getByText("190.00")).toBeInTheDocument();
    expect(within(row).getByText("-$100.00")).toHaveClass("text-loss");
    expect(within(row).getByText("-5.00%")).toHaveClass("text-loss");
  });

  it("selects a ticker when it is clicked", async () => {
    const onSelect = vi.fn();
    render(<PositionsTable positions={portfolio.positions} focus={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole("button", { name: "AAPL" }));
    expect(onSelect).toHaveBeenCalledWith("AAPL");
  });

  it("invites a first trade when there are no positions", () => {
    render(<PositionsTable positions={[]} focus={null} onSelect={vi.fn()} />);
    expect(screen.getByText(/No open positions/)).toBeInTheDocument();
  });
});
