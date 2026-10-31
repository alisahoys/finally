import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Trade } from "@/data/types";
import { TradeBar } from "./TradeBar";

const fill: Trade = {
  id: "1",
  ticker: "AAPL",
  side: "sell",
  quantity: 2.5,
  price: 190.5,
  executed_at: "2026-10-28T14:00:00Z",
};

describe("TradeBar", () => {
  it("submits the focused ticker with the chosen side and confirms the fill", async () => {
    const onTrade = vi.fn().mockResolvedValue(fill);
    render(<TradeBar ticker="AAPL" onTrade={onTrade} />);
    await userEvent.type(screen.getByLabelText("Quantity"), "2.5");
    await userEvent.click(screen.getByRole("button", { name: "Sell" }));
    expect(onTrade).toHaveBeenCalledWith("AAPL", 2.5, "sell");
    expect(await screen.findByRole("status")).toHaveTextContent("Sold 2.5 AAPL at $190.50");
  });

  it("shows the reason a trade was rejected", async () => {
    const onTrade = vi.fn().mockRejectedValue(new Error("Insufficient cash"));
    render(<TradeBar ticker="AAPL" onTrade={onTrade} />);
    await userEvent.type(screen.getByLabelText("Quantity"), "1000");
    await userEvent.click(screen.getByRole("button", { name: "Buy" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Insufficient cash");
    expect(screen.getByRole("status")).toHaveClass("text-loss");
  });

  it("follows the focused ticker", () => {
    const { rerender } = render(<TradeBar ticker="AAPL" onTrade={vi.fn()} />);
    rerender(<TradeBar ticker="NVDA" onTrade={vi.fn()} />);
    expect(screen.getByLabelText("Ticker")).toHaveValue("NVDA");
  });
});
