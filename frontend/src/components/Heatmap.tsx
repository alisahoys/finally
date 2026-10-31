import { formatPercent } from "@/data/format";
import { buildTreemap, heatColor, type TreemapNode } from "@/data/treemap";
import type { Position } from "@/data/types";
import { Panel } from "./Panel";

interface TileProps {
  node: TreemapNode;
  positions: Map<string, Position>;
  focus: string | null;
  onSelect: (ticker: string) => void;
}

function Tile({ node, positions, focus, onSelect }: TileProps) {
  const size = { flexGrow: node.weight, flexBasis: 0 };
  if (node.kind === "split") {
    return (
      <div className="flex min-h-0 min-w-0 gap-px" style={{ ...size, flexDirection: node.axis }}>
        {node.children.map((child, index) => (
          <Tile key={index} node={child} positions={positions} focus={focus} onSelect={onSelect} />
        ))}
      </div>
    );
  }
  const { ticker } = node.item;
  const { pnl_percent } = positions.get(ticker)!;
  return (
    <button
      type="button"
      onClick={() => onSelect(ticker)}
      aria-pressed={ticker === focus}
      data-testid={`tile-${ticker}`}
      style={{ ...size, background: heatColor(pnl_percent) }}
      className={`flex min-h-0 min-w-0 flex-col items-center justify-center overflow-hidden p-0.5 text-white ${
        ticker === focus ? "outline-2 -outline-offset-2 outline-focus" : ""
      }`}
    >
      <span className="font-semibold">{ticker}</span>
      <span className="text-sm">{formatPercent(pnl_percent)}</span>
    </button>
  );
}

interface HeatmapProps {
  positions: Position[];
  focus: string | null;
  onSelect: (ticker: string) => void;
}

/** Treemap of positions: area shows portfolio weight, color shows P&L. */
export function Heatmap({ positions, focus, onSelect }: HeatmapProps) {
  const tree = buildTreemap(
    positions.map(({ ticker, market_value }) => ({ ticker, weight: market_value })),
  );
  const byTicker = new Map(positions.map((position) => [position.ticker, position]));
  return (
    <Panel title="Portfolio heatmap" className="max-lg:h-72">
      <div className="flex min-h-0 flex-1 p-1 pt-0">
        {tree ? (
          <Tile node={tree} positions={byTicker} focus={focus} onSelect={onSelect} />
        ) : (
          <p className="m-auto max-w-52 text-center text-sm text-muted">
            Your positions appear here, sized by weight and colored by profit or loss.
          </p>
        )}
      </div>
    </Panel>
  );
}
