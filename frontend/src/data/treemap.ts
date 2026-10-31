export interface TreemapItem {
  ticker: string;
  weight: number;
}

export type TreemapNode =
  | { kind: "leaf"; item: TreemapItem; weight: number }
  | { kind: "split"; axis: "row" | "column"; children: TreemapNode[]; weight: number };

const totalWeight = (items: TreemapItem[]) => items.reduce((sum, item) => sum + item.weight, 0);

/** Return the index that divides weight-sorted items into two nearly equal halves. */
function balancedSplit(items: TreemapItem[]) {
  const half = totalWeight(items) / 2;
  let running = 0;
  for (let index = 0; index < items.length - 1; index++) {
    running += items[index].weight;
    if (running >= half) return index + 1;
  }
  return items.length - 1;
}

function layout(items: TreemapItem[], axis: "row" | "column"): TreemapNode {
  if (items.length === 1) return { kind: "leaf", item: items[0], weight: items[0].weight };
  const split = balancedSplit(items);
  const next = axis === "row" ? "column" : "row";
  return {
    kind: "split",
    axis,
    weight: totalWeight(items),
    children: [layout(items.slice(0, split), next), layout(items.slice(split), next)],
  };
}

/** Build a nested flex layout: heaviest first, halved by weight, alternating axis. */
export function buildTreemap(items: TreemapItem[]): TreemapNode | null {
  if (items.length === 0) return null;
  return layout([...items].sort((a, b) => b.weight - a.weight), "row");
}

const FULL_TINT_PERCENT = 5;

/** Tint a tile by P&L: stronger with size, saturating at a 5% move. */
export function heatColor(pnlPercent: number) {
  if (pnlPercent === 0) return "var(--color-raised)";
  const tone = pnlPercent > 0 ? "--color-gain-deep" : "--color-loss-deep";
  const strength = Math.min(Math.abs(pnlPercent) / FULL_TINT_PERCENT, 1);
  const mix = Math.round(35 + strength * 65);
  return `color-mix(in srgb, var(${tone}) ${mix}%, var(--color-panel))`;
}
