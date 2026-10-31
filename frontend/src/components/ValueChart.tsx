import { useMemo } from "react";
import { snapshotPoints } from "@/data/history";
import type { Snapshot } from "@/data/types";
import { LineChart } from "./LineChart";
import { Panel } from "./Panel";

/** Total portfolio value over time, split around where the history began. */
export function ValueChart({ snapshots }: { snapshots: Snapshot[] }) {
  const points = useMemo(() => snapshotPoints(snapshots), [snapshots]);
  return (
    <Panel title="Portfolio value" className="max-lg:h-72">
      <div className="min-h-0 flex-1 px-1 pb-1">
        {points.length > 1 ? (
          <LineChart points={points} baseline={points[0].value} />
        ) : (
          <p className="flex h-full items-center justify-center text-sm text-muted">
            The value line starts after the next snapshot.
          </p>
        )}
      </div>
    </Panel>
  );
}
