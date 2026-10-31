import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/data/api";
import { ChatPanel, describeAction } from "./ChatPanel";

afterEach(() => vi.restoreAllMocks());

async function sendMessage(text: string) {
  await userEvent.type(screen.getByLabelText("Message FinAlly"), `${text}{Enter}`);
}

describe("describeAction", () => {
  it("describes trades and watchlist changes", () => {
    const base = { ticker: "NVDA", status: "ok" } as const;
    expect(
      describeAction({ ...base, type: "trade", side: "buy", quantity: 5, price: 875.2 }),
    ).toBe("Bought 5 NVDA at $875.20");
    expect(describeAction({ ...base, type: "watchlist", action: "remove" })).toBe(
      "Removed NVDA from your watchlist",
    );
    expect(
      describeAction({
        type: "trade",
        ticker: "TSLA",
        side: "sell",
        quantity: 100,
        status: "error",
        error: "Insufficient shares",
      }),
    ).toBe("Could not sell 100 TSLA: Insufficient shares");
  });
});

describe("ChatPanel", () => {
  it("shows the reply with executed actions and refreshes the account", async () => {
    vi.spyOn(api, "chat").mockResolvedValue({
      message: "Buying 5 NVDA.",
      actions: [
        { type: "trade", ticker: "NVDA", side: "buy", quantity: 5, status: "ok", price: 875.2 },
      ],
    });
    const onActions = vi.fn();
    render(<ChatPanel onActions={onActions} />);
    await sendMessage("Buy 5 NVDA");
    expect(await screen.findByText("Buying 5 NVDA.")).toBeInTheDocument();
    expect(screen.getByText("Bought 5 NVDA at $875.20")).toBeInTheDocument();
    expect(onActions).toHaveBeenCalledOnce();
  });

  it("does not refresh the account when nothing executed", async () => {
    vi.spyOn(api, "chat").mockResolvedValue({ message: "Hello.", actions: [] });
    const onActions = vi.fn();
    render(<ChatPanel onActions={onActions} />);
    await sendMessage("Hi");
    await screen.findByText("Hello.");
    expect(onActions).not.toHaveBeenCalled();
  });

  it("shows a loading indicator until the reply arrives", async () => {
    let reply!: (value: { message: string; actions: [] }) => void;
    vi.spyOn(api, "chat").mockReturnValue(new Promise((resolve) => (reply = resolve)));
    render(<ChatPanel onActions={vi.fn()} />);
    await sendMessage("Hi");
    expect(screen.getByText("FinAlly is thinking")).toBeInTheDocument();
    reply({ message: "Hello.", actions: [] });
    await screen.findByText("Hello.");
    expect(screen.queryByText("FinAlly is thinking")).not.toBeInTheDocument();
  });

  it("explains a failed request", async () => {
    vi.spyOn(api, "chat").mockRejectedValue(new Error("offline"));
    render(<ChatPanel onActions={vi.fn()} />);
    await sendMessage("Hi");
    expect(await screen.findByText(/did not answer/)).toBeInTheDocument();
  });
});
