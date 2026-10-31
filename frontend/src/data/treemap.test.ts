import { describe, expect, it } from "vitest";
import { buildTreemap, heatColor, type TreemapNode } from "./treemap";

const leaves = (node: TreemapNode): string[] =>
  node.kind === "leaf" ? [node.item.ticker] : node.children.flatMap(leaves);

describe("buildTreemap", () => {
  it("returns nothing for no positions", () => {
    expect(buildTreemap([])).toBeNull();
  });

  it("gives a single position the whole area", () => {
    expect(buildTreemap([{ ticker: "AAPL", weight: 5 }])).toMatchObject({ kind: "leaf" });
  });

  it("orders heaviest first and keeps every position", () => {
    const tree = buildTreemap([
      { ticker: "C", weight: 1 },
      { ticker: "A", weight: 5 },
      { ticker: "B", weight: 3 },
    ]);
    expect(leaves(tree!)).toEqual(["A", "B", "C"]);
    expect(tree!.weight).toBe(9);
  });

  it("separates a dominant position from the rest and alternates axis", () => {
    const tree = buildTreemap([
      { ticker: "A", weight: 6 },
      { ticker: "B", weight: 2 },
      { ticker: "C", weight: 1 },
    ]);
    if (tree?.kind !== "split") throw new Error("expected a split");
    expect(tree.axis).toBe("row");
    expect(leaves(tree.children[0])).toEqual(["A"]);
    expect(tree.children[1]).toMatchObject({ kind: "split", axis: "column", weight: 3 });
  });
});

describe("heatColor", () => {
  it("is neutral with no P&L", () => {
    expect(heatColor(0)).toBe("var(--color-raised)");
  });

  it("uses green for profit and red for loss, saturating at 5%", () => {
    expect(heatColor(1)).toContain("--color-gain-deep) 48%");
    expect(heatColor(-5)).toContain("--color-loss-deep) 100%");
    expect(heatColor(-40)).toContain("--color-loss-deep) 100%");
  });
});
