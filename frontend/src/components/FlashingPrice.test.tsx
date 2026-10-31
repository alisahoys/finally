import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Direction, PriceUpdate } from "@/data/types";
import { FlashingPrice } from "./FlashingPrice";

const update = (price: number, timestamp: number, direction: Direction) =>
  ({ price, timestamp, direction }) as PriceUpdate;

describe("FlashingPrice", () => {
  it("flashes green on an uptick and red on a downtick", () => {
    const { rerender } = render(<FlashingPrice update={update(190.5, 1, "up")} />);
    expect(screen.getByText("190.50")).toHaveClass("flash-up");
    rerender(<FlashingPrice update={update(190.25, 2, "down")} />);
    expect(screen.getByText("190.25")).toHaveClass("flash-down");
  });

  it("does not flash when the price is unchanged", () => {
    render(<FlashingPrice update={update(190.5, 1, "flat")} />);
    const price = screen.getByText("190.50");
    expect(price).not.toHaveClass("flash-up");
    expect(price).not.toHaveClass("flash-down");
  });

  it("restarts the animation on each new tick, even in the same direction", () => {
    const { rerender } = render(<FlashingPrice update={update(190.5, 1, "up")} />);
    const first = screen.getByText("190.50");
    rerender(<FlashingPrice update={update(190.75, 2, "up")} />);
    expect(screen.getByText("190.75")).not.toBe(first);
  });

  it("keeps the same element when the tick has not changed", () => {
    const { rerender } = render(<FlashingPrice update={update(190.5, 1, "up")} />);
    const first = screen.getByText("190.50");
    rerender(<FlashingPrice update={update(190.5, 1, "up")} />);
    expect(screen.getByText("190.50")).toBe(first);
  });
});
