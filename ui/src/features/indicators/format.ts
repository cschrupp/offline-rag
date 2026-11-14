export type IndicatorDisplayKind =
  | "proportion"
  | "ranking_score_0_1"
  | "count"
  | "points"
  | "duration"
  | "byte_quantity"
  | "throughput"
  | "ratio"
  | "scalar"
  | "percentage_point_delta"
  | "relative_percent_delta"
  | "status";

export function formatIndicatorValue(
  value: number | string,
  kind: IndicatorDisplayKind,
  unit?: string,
  precision = 3,
): string {
  if (kind === "status") return String(value);
  if (typeof value !== "number" || !Number.isFinite(value)) return "Unavailable";
  switch (kind) {
    case "proportion":
      return `${(value * 100).toFixed(precision)}%`;
    case "ranking_score_0_1":
    case "scalar":
      return value.toFixed(precision);
    case "count":
      return new Intl.NumberFormat("en").format(value);
    case "points":
      return `${new Intl.NumberFormat("en").format(value)} points`;
    case "duration":
      return unit === "ms"
        ? `${(value / 1000).toFixed(precision)} s`
        : `${value.toFixed(precision)} s`;
    case "byte_quantity": {
      if (Math.abs(value) < 1024) return `${value} B`;
      const units = ["KiB", "MiB", "GiB", "TiB"];
      let scaled = value / 1024;
      let index = 0;
      while (Math.abs(scaled) >= 1024 && index < units.length - 1) {
        scaled /= 1024;
        index += 1;
      }
      return `${Number(scaled.toFixed(precision))} ${units[index]}`;
    }
    case "throughput":
      return `${value.toFixed(precision)} ${unit ?? "units/s"}`;
    case "ratio":
      return `${value.toFixed(precision)}×`;
    case "percentage_point_delta":
      return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(precision)} pp`;
    case "relative_percent_delta":
      return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(precision)}%`;
  }
}
