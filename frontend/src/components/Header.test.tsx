import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Portfolio } from "@/data/types";
import { Header } from "./Header";

const portfolio: Portfolio = {
  cash_balance: 8095,
  total_value: 10012.4,
  unrealized_pnl: 12.4,
  positions: [],
};

describe("Header", () => {
  it("shows account totals and marks a gain", () => {
    render(<Header portfolio={portfolio} status="connected" />);
    expect(screen.getByText("$10,012.40")).toBeInTheDocument();
    expect(screen.getByText("$8,095.00")).toBeInTheDocument();
    expect(screen.getByText("+$12.40")).toHaveClass("text-gain");
  });

  it("shows placeholders before the portfolio loads", () => {
    render(<Header portfolio={null} status="reconnecting" />);
    expect(screen.getAllByText("--")).toHaveLength(3);
  });

  it.each([
    ["connected", "Live", "bg-gain"],
    ["reconnecting", "Reconnecting", "bg-focus"],
    ["disconnected", "Disconnected", "bg-loss"],
  ] as const)("shows the %s state", (status, label, dot) => {
    render(<Header portfolio={portfolio} status={status} />);
    const indicator = screen.getByRole("status");
    expect(indicator).toHaveTextContent(label);
    expect(indicator.querySelector("span")).toHaveClass(dot);
  });
});
