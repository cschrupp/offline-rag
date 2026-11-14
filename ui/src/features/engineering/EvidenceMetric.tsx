import type { Metric } from "./evidenceTypes";

import { formatIndicatorValue } from "../indicators/format";

function formatMeasured(metric: Metric): string {
  const value = metric.value;
  if (value === null) return "Unavailable";
  let text: string;
  if (metric.display_kind) {
    text = formatIndicatorValue(
      value,
      metric.display_kind,
      metric.unit,
      metric.precision,
    );
  } else {
    return "Unavailable (missing indicator definition)";
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
