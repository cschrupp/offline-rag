import type { Metric } from "./evidenceTypes";
import { EvidenceMetric } from "./EvidenceMetric";

export type BarRow = {
  id: string;
  label: string;
  metric: Metric;
};

type Props = {
  caption: string;
  rows: BarRow[];
  /** Fixed domain for measured values in [0, 1]. */
  domainMax?: number;
  valueHeading?: string;
};

/**
 * Horizontal bar chart for 0–1 ranking metrics.
 * Exact values are always shown as text; bar length is supplemental.
 */
export function MetricBarChart({
  caption,
  rows,
  domainMax = 1,
  valueHeading = "Value",
}: Props) {
  return (
    <figure className="engineering-chart" data-testid="metric-bar-chart">
      <figcaption className="engineering-chart-caption">{caption}</figcaption>
      <ol className="engineering-bar-list" data-domain-max={String(domainMax)}>
        {rows.map((row) => {
          const measured =
            row.metric.availability === "measured" &&
            typeof row.metric.value === "number";
          const ratio = measured
            ? Math.max(0, Math.min(1, row.metric.value! / domainMax))
            : 0;
          return (
            <li key={row.id} className="engineering-bar-row" data-arm-id={row.id}>
              <div className="engineering-bar-label">{row.label}</div>
              <div className="engineering-bar-track" aria-hidden={!measured}>
                {measured ? (
                  <div
                    className="engineering-bar-fill"
                    style={{ width: `${ratio * 100}%` }}
                    data-bar-ratio={String(ratio)}
                  />
                ) : (
                  <div className="engineering-bar-empty" />
                )}
              </div>
              <div className="engineering-bar-value">
                <span className="visually-hidden">{valueHeading}: </span>
                <EvidenceMetric metric={row.metric} />
              </div>
            </li>
          );
        })}
      </ol>
      <p className="muted engineering-chart-scale" style={{ margin: 0 }}>
        Scale {domainMax === 1 ? "0.0 → 1.0" : `0 → ${domainMax}`} (fixed domain)
      </p>
    </figure>
  );
}
