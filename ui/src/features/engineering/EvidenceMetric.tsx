import type { Metric } from "./evidenceTypes";

function formatMeasured(metric: Metric): string {
  const value = metric.value;
  if (value === null) return "Unavailable";
  let text: string;
  if (metric.unit === "s") {
    text = `${value} s`;
  } else if (metric.unit === "ms") {
    text = `${value} ms`;
  } else if (metric.unit === "bytes") {
    const gib = value / (1024 ** 3);
    text = `${gib.toFixed(2)} GiB`;
  } else if (metric.unit) {
    text = `${value} ${metric.unit}`;
  } else if (typeof value === "number" && value >= 0 && value <= 1) {
    // Rates presented as decimals in source stay decimal unless clearly percent.
    text = String(value);
  } else {
    text = String(value);
  }
  if (metric.value_qualifier === "approximate") {
    return `≈ ${text}`;
  }
  return text;
}

type Props = {
  metric: Metric;
  className?: string;
};

export function EvidenceMetric({ metric, className }: Props) {
  let label: string;
  if (metric.availability === "measured") {
    label = formatMeasured(metric);
  } else if (metric.availability === "unavailable") {
    label = "Unavailable";
  } else if (metric.availability === "unevaluable") {
    label = "Unevaluable";
  } else if (metric.availability === "not_applicable") {
    label = "Not applicable";
  } else {
    label = "Unavailable";
  }
  return <span className={className}>{label}</span>;
}
