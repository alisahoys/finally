import type { PriceMap, Snapshot } from "./types";

export interface ChartPoint {
  time: number;
  value: number;
}

export type PriceHistory = Record<string, ChartPoint[]>;

const MAX_POINTS = 3600;

/** Append each streamed price to its ticker's history, skipping repeated timestamps. */
export function appendPrices(history: PriceHistory, prices: PriceMap) {
  for (const { ticker, price, timestamp } of Object.values(prices)) {
    const points = (history[ticker] ??= []);
    if (timestamp <= (points.at(-1)?.time ?? 0)) continue;
    points.push({ time: timestamp, value: price });
    if (points.length > MAX_POINTS) points.shift();
  }
}

/** Convert snapshots to chart points; snapshots in the same second keep the latest value. */
export function snapshotPoints(snapshots: Snapshot[]): ChartPoint[] {
  const bySecond = new Map<number, number>();
  for (const { recorded_at, total_value } of snapshots) {
    bySecond.set(Date.parse(recorded_at) / 1000, total_value);
  }
  return [...bySecond].map(([time, value]) => ({ time, value }));
}
