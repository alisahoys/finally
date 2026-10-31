import { describe, expect, it } from "vitest";
import { appendPrices, snapshotPoints, type PriceHistory } from "./history";
import type { PriceMap, PriceUpdate } from "./types";

const tick = (price: number, timestamp: number): PriceMap => ({
  AAPL: { ticker: "AAPL", price, timestamp } as PriceUpdate,
});

describe("appendPrices", () => {
  it("accumulates points per ticker and skips repeated timestamps", () => {
    const history: PriceHistory = {};
    appendPrices(history, tick(190, 1));
    appendPrices(history, tick(191, 2));
    appendPrices(history, tick(191, 2));
    expect(history.AAPL).toEqual([
      { time: 1, value: 190 },
      { time: 2, value: 191 },
    ]);
  });
});

describe("snapshotPoints", () => {
  it("converts timestamps and collapses snapshots in the same second", () => {
    const points = snapshotPoints([
      { total_value: 10000, recorded_at: "2026-10-28T14:00:00Z" },
      { total_value: 10010, recorded_at: "2026-10-28T14:00:00Z" },
      { total_value: 10020, recorded_at: "2026-10-28T14:00:30Z" },
    ]);
    const start = Date.UTC(2026, 9, 28, 14) / 1000;
    expect(points).toEqual([
      { time: start, value: 10010 },
      { time: start + 30, value: 10020 },
    ]);
  });
});
