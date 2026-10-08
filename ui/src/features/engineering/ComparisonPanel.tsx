import type { Metric } from "./evidenceTypes";
import { EvidenceMetric } from "./EvidenceMetric";

export type ComparisonMetric = {
  label: string;
  metric: Metric;
};

export type ComparisonVariant = {
  id: string;
  label: string;
  metrics: ComparisonMetric[];
};

type Props = {
  title: string;
  variants: ComparisonVariant[];
  "data-testid"?: string;
};

/** Separate quality or latency panel — no shared synthetic axis. */
export function ComparisonPanel({
  title,
  variants,
  "data-testid": testId,
}: Props) {
  return (
    <section
      className="engineering-comparison-panel stack"
      aria-labelledby={`comparison-${title.replace(/\s+/g, "-").toLowerCase()}`}
      data-testid={testId}
    >
      <h3
        id={`comparison-${title.replace(/\s+/g, "-").toLowerCase()}`}
        style={{ margin: 0 }}
      >
        {title}
      </h3>
      <ul className="engineering-comparison-list">
        {variants.map((variant) => (
          <li key={variant.id} data-variant-id={variant.id}>
            <div className="engineering-comparison-variant">{variant.label}</div>
            <dl className="engineering-comparison-metrics">
              {variant.metrics.map((item) => (
                <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>
                    <EvidenceMetric metric={item.metric} />
                  </dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </section>
  );
}
