export interface Point {
  time: number;
  value: number;
}

export interface Change {
  absolute: number;
  percent: number;
}

export function changeFrom(value: number, reference: number): Change {
  const absolute = value - reference;
  return { absolute, percent: reference ? (absolute / reference) * 100 : 0 };
}

export function extremes(points: Point[]): { high: Point; low: Point } | null {
  if (points.length === 0) return null;
  return points.reduce(
    ({ high, low }, point) => ({
      high: point.value > high.value ? point : high,
      low: point.value < low.value ? point : low,
    }),
    { high: points[0], low: points[0] },
  );
}

/** Inversioni di tendenza: contano solo i movimenti pari ad almeno `share` dell'escursione. */
export function turningPoints(points: Point[], share = 0.25, limit = 6): Point[] {
  const range = extremes(points);
  if (!range || range.high.value === range.low.value) return [];
  const threshold = (range.high.value - range.low.value) * share;
  const pivots: Point[] = [];
  let extreme = points[0];
  let direction = 0;
  for (const point of points.slice(1)) {
    if (direction >= 0 && point.value >= extreme.value) {
      extreme = point;
      direction = direction || 1;
    } else if (direction <= 0 && point.value <= extreme.value) {
      extreme = point;
      direction = direction || -1;
    } else if (Math.abs(point.value - extreme.value) >= threshold) {
      if (extreme !== points[0]) pivots.push(extreme);
      direction = -direction;
      extreme = point;
    }
  }
  return pivots
    .filter((point) => point !== range.high && point !== range.low)
    .slice(-limit);
}

export type LiveState = "live" | "delayed" | "closed";

const LIVE_MAX_AGE_S = 180;

/** LIVE solo se il dato e' davvero recente: un mercato aperto con dati vecchi e' "ritardato". */
export function liveState(isOpen: boolean, marketTime: number | null, nowSeconds: number): LiveState {
  if (!isOpen) return "closed";
  return marketTime !== null && nowSeconds - marketTime <= LIVE_MAX_AGE_S ? "live" : "delayed";
}

/** Aggiunge l'ultima quotazione in coda alla serie, se piu' recente dell'ultimo punto. */
export function withLastPrice(points: Point[], time: number | null, price: number | null): Point[] {
  const last = points[points.length - 1];
  if (!last || time === null || price === null || time <= last.time) return points;
  return [...points, { time, value: price }];
}
