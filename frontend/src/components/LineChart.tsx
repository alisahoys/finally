import {
  BaselineSeries,
  ColorType,
  LineSeries,
  LineStyle,
  createChart,
  type DeepPartial,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type SeriesDataItemTypeMap,
  type TimeChartOptions,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { ChartPoint } from "@/data/history";
import { colors } from "@/data/theme";

const formatTime = (time: number) =>
  new Date(time * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

const NO_POINTS: ChartPoint[] = [];

type ChartSeries = ISeriesApi<"Line"> | ISeriesApi<"Baseline">;
type SeriesPoint = SeriesDataItemTypeMap["Line"];

const toSeriesPoint = ({ time, value }: ChartPoint): SeriesPoint => ({
  time: time as UTCTimestamp,
  value,
});

interface LineChartProps {
  points?: ChartPoint[];
  /** Changes whenever `points` grows in place. */
  revision?: unknown;
  /** Plain axes-free rendering for sparklines. */
  compact?: boolean;
  /** Show the TradingView logo; the license needs it once on the page. */
  attribution?: boolean;
  color?: string;
  /** Color above and below this value instead of using one line color. */
  baseline?: number;
  /** Dashed horizontal reference, labeled "Open". */
  openPrice?: number;
}

function chartOptions(compact: boolean, attribution: boolean): DeepPartial<TimeChartOptions> {
  return {
    autoSize: true,
    handleScale: false,
    handleScroll: false,
    layout: {
      attributionLogo: attribution,
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: colors.muted,
      fontFamily: "inherit",
      fontSize: 12,
    },
    grid: {
      vertLines: { visible: false },
      horzLines: { color: colors.line, visible: !compact },
    },
    crosshair: { horzLine: { visible: !compact }, vertLine: { visible: !compact } },
    leftPriceScale: { visible: false },
    rightPriceScale: { visible: !compact, borderVisible: false },
    timeScale: {
      visible: !compact,
      borderVisible: false,
      timeVisible: true,
      secondsVisible: true,
      tickMarkFormatter: (time: number) => formatTime(time),
    },
    localization: { timeFormatter: (time: number) => formatTime(time) },
  };
}

function addSeries(chart: IChartApi, baseline: number | undefined): ChartSeries {
  const shared = { lineWidth: 2, priceLineVisible: false, lastValueVisible: false } as const;
  if (baseline === undefined) return chart.addSeries(LineSeries, shared);
  return chart.addSeries(BaselineSeries, {
    ...shared,
    topLineColor: colors.gain,
    bottomLineColor: colors.loss,
    topFillColor1: `${colors.gain}38`,
    topFillColor2: `${colors.gain}00`,
    bottomFillColor1: `${colors.loss}00`,
    bottomFillColor2: `${colors.loss}38`,
  });
}

/** One Lightweight Charts line: sparkline, price chart or portfolio value. */
export function LineChart({
  points = NO_POINTS,
  revision,
  compact = false,
  attribution = false,
  color,
  baseline,
  openPrice,
}: LineChartProps) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi>(null);
  const series = useRef<ChartSeries>(null);
  const loaded = useRef<ChartPoint[]>(null);
  const openLine = useRef<IPriceLine>(null);
  const hasBaseline = baseline !== undefined;

  useEffect(() => {
    chart.current = createChart(container.current!, chartOptions(compact, attribution));
    series.current = addSeries(chart.current, hasBaseline ? 0 : undefined);
    return () => {
      chart.current?.remove();
      loaded.current = null;
      openLine.current = null;
    };
  }, [compact, attribution, hasBaseline]);

  useEffect(() => {
    if (color) series.current?.applyOptions({ color });
    if (hasBaseline) {
      series.current?.applyOptions({ baseValue: { type: "price", price: baseline } });
    }
  }, [color, baseline, hasBaseline]);

  useEffect(() => {
    if (openLine.current) series.current?.removePriceLine(openLine.current);
    openLine.current = null;
    if (openPrice === undefined) return;
    openLine.current = series.current!.createPriceLine({
      price: openPrice,
      color: colors.muted,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "Open",
    });
  }, [openPrice]);

  useEffect(() => {
    const last = points.at(-1);
    if (loaded.current === points && last) {
      series.current?.update(toSeriesPoint(last));
    } else {
      series.current?.setData(points.map(toSeriesPoint));
      loaded.current = points;
    }
    chart.current?.timeScale().fitContent();
  }, [points, revision]);

  return <div ref={container} className="size-full" />;
}
