import { AreaSeries, ColorType, createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { Chart } from "../api";

const cssColor = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function palette(trendUp: boolean) {
  const line = cssColor(trendUp ? "--up" : "--down");
  return { lineColor: line, topColor: `${line}33`, bottomColor: `${line}00` };
}

/** Linea senza assi ne' griglie: i valori si leggono spostando il cursore. */
export default function PriceChart({ points, intraday }: { points: Chart["points"]; intraday: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    const element = host.current!;
    const instance = createChart(element, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: cssColor("--muted"), fontFamily: "inherit" },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { visible: false },
      leftPriceScale: { visible: false },
      timeScale: { visible: false },
      crosshair: { horzLine: { visible: false, labelVisible: false } },
      // Lo scorrimento della pagina resta alla pagina, anche da touch.
      handleScroll: false,
      handleScale: false,
      localization: { locale: "it-IT" },
    });
    chart.current = instance;
    series.current = instance.addSeries(AreaSeries, { lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerRadius: 3 });
    return () => {
      instance.remove();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    const data = points.map(({ time, value }) => ({ time: time as UTCTimestamp, value }));
    const paint = () => {
      const trendUp = data.length < 2 || data[data.length - 1].value >= data[0].value;
      series.current?.applyOptions(palette(trendUp));
      chart.current?.applyOptions({ layout: { textColor: cssColor("--muted") } });
    };
    series.current?.setData(data);
    chart.current?.applyOptions({ timeScale: { timeVisible: intraday } });
    chart.current?.timeScale().fitContent();
    paint();
    // I colori seguono il cambio di tema.
    const observer = new MutationObserver(paint);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [points, intraday]);

  return <div ref={host} className="h-full w-full" />;
}
