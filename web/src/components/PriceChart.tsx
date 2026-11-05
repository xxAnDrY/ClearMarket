import {
  AreaSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import { changeFrom, extremes, turningPoints, type Point } from "../chartMath";
import { formatExact, formatNumber, formatSigned } from "../format";

const cssColor = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const tooltipTime = new Intl.DateTimeFormat("it", {
  day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
});

interface PriceChartProps {
  points: Point[];
  /** Chiusura precedente in 1D, primo punto del periodo negli altri casi. */
  reference: number | null;
  referenceLabel: string;
  currency: string;
}

/** Solo punti: i valori di massimo e minimo stanno nella riga sotto il grafico. */
function buildMarkers(points: Point[]): SeriesMarker<Time>[] {
  const range = extremes(points);
  if (!range || range.high.value === range.low.value) return [];
  const pivots = turningPoints(points).map((point): SeriesMarker<Time> => ({
    time: point.time as UTCTimestamp, position: "inBar", shape: "circle", size: 0.5, color: cssColor("--muted"),
  }));
  const high: SeriesMarker<Time> = {
    time: range.high.time as UTCTimestamp, position: "aboveBar", shape: "circle", size: 0.6,
    color: cssColor("--up"),
  };
  const low: SeriesMarker<Time> = {
    time: range.low.time as UTCTimestamp, position: "belowBar", shape: "circle", size: 0.6,
    color: cssColor("--down"),
  };
  return [...pivots, high, low].sort((first, second) => Number(first.time) - Number(second.time));
}

/** Linea senza assi ne' griglie: i valori si leggono dal tooltip che segue il cursore. */
export default function PriceChart({ points, reference, referenceLabel, currency }: PriceChartProps) {
  const host = useRef<HTMLDivElement>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);
  const markers = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const baseline = useRef<IPriceLine | null>(null);
  // Letti dal gestore del cursore, che non deve provocare render di React.
  const live = useRef({ reference, referenceLabel, currency });
  live.current = { reference, referenceLabel, currency };

  useEffect(() => {
    const element = host.current!;
    const box = tooltip.current!;
    const instance = createChart(element, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: cssColor("--muted"), fontFamily: "inherit", fontSize: 10 },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { visible: false, scaleMargins: { top: 0.2, bottom: 0.2 } },
      leftPriceScale: { visible: false },
      timeScale: { visible: false },
      crosshair: {
        horzLine: { visible: true, labelVisible: false, style: LineStyle.Dotted },
        vertLine: { labelVisible: false, style: LineStyle.Dotted },
      },
      // Lo scorrimento della pagina resta alla pagina, anche da touch.
      handleScroll: false,
      handleScale: false,
      localization: { locale: "it-IT" },
    });
    const area = instance.addSeries(AreaSeries, { lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerRadius: 4 });
    chart.current = instance;
    series.current = area;
    markers.current = createSeriesMarkers(area, []);

    const onMove = (param: MouseEventParams<Time>) => {
      const data = param.seriesData.get(area) as { value?: number } | undefined;
      const inside = param.point && param.point.x >= 0 && param.point.y >= 0
        && param.point.x <= element.clientWidth && param.point.y <= element.clientHeight;
      if (!inside || !param.time || data?.value === undefined) {
        box.style.opacity = "0";
        return;
      }
      const { reference: base, referenceLabel: label, currency: unit } = live.current;
      const [price, time, change, against] = box.children as unknown as HTMLElement[];
      price.textContent = formatExact(data.value, unit);
      time.textContent = tooltipTime.format(new Date(Number(param.time) * 1000));
      if (base) {
        const { absolute, percent } = changeFrom(data.value, base);
        change.textContent = `${formatSigned(absolute, formatExact(absolute, unit, data.value))} / ${formatSigned(percent, `${formatNumber(percent)}%`)}`;
        change.style.color = cssColor(absolute >= 0 ? "--up" : "--down");
        against.textContent = label;
      } else {
        change.textContent = "";
        against.textContent = "";
      }
      // Scritture dirette sul DOM: il tooltip segue il mouse senza render di React.
      const x = Math.min(param.point!.x + 12, element.clientWidth - box.offsetWidth - 4);
      const flipped = x < param.point!.x ? param.point!.x - box.offsetWidth - 12 : x;
      box.style.transform = `translate(${Math.max(flipped, 4)}px, ${Math.max(param.point!.y - box.offsetHeight - 10, 4)}px)`;
      box.style.opacity = "1";
    };
    instance.subscribeCrosshairMove(onMove);

    return () => {
      instance.unsubscribeCrosshairMove(onMove);
      instance.remove();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    const data = points.map(({ time, value }) => ({ time: time as UTCTimestamp, value }));
    const paint = () => {
      const first = reference ?? data[0]?.value ?? 0;
      const trendUp = data.length === 0 || data[data.length - 1].value >= first;
      const line = cssColor(trendUp ? "--up" : "--down");
      series.current?.applyOptions({ lineColor: line, topColor: `${line}33`, bottomColor: `${line}00` });
      chart.current?.applyOptions({ layout: { textColor: cssColor("--muted") } });
      markers.current?.setMarkers(buildMarkers(points));
      if (baseline.current) series.current?.removePriceLine(baseline.current);
      baseline.current = reference && series.current
        ? series.current.createPriceLine({ price: reference, color: cssColor("--muted"), lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false })
        : null;
    };
    series.current?.setData(data);
    chart.current?.timeScale().fitContent();
    paint();
    // I colori seguono il cambio di tema.
    const observer = new MutationObserver(paint);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [points, reference, currency]);

  return (
    <div className="relative h-full w-full">
      <div ref={host} className="h-full w-full" />
      <div
        ref={tooltip}
        role="status"
        className="pointer-events-none absolute top-0 left-0 z-10 rounded-xl border border-line bg-surface/95 px-2.5 py-1.5 text-xs whitespace-nowrap tabular-nums opacity-0 shadow-md backdrop-blur-sm"
      >
        <p className="text-sm font-semibold" />
        <p className="text-[11px] text-muted" />
        <p className="font-semibold" />
        <p className="text-[10px] text-muted" />
      </div>
    </div>
  );
}
