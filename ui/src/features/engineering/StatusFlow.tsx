type FlowStep = {
  label: string;
  value: string;
};

type Props = {
  title: string;
  steps: FlowStep[];
  aside?: { label: string; value: string };
  explanation?: string;
  "data-testid"?: string;
};

/** Ordered status/decision flow — not a chart. */
export function StatusFlow({
  title,
  steps,
  aside,
  explanation,
  "data-testid": testId,
}: Props) {
  return (
    <section
      className="engineering-status-flow stack"
      aria-labelledby={`status-flow-${title.replace(/\s+/g, "-").toLowerCase()}`}
      data-testid={testId}
    >
      <h3
        id={`status-flow-${title.replace(/\s+/g, "-").toLowerCase()}`}
        className="visually-hidden"
      >
        {title}
      </h3>
      <ol className="engineering-flow-steps">
        {steps.map((step) => (
          <li key={`${step.label}-${step.value}`}>
            <div className="engineering-flow-label">{step.label}</div>
            <div className="engineering-flow-value">{step.value}</div>
          </li>
        ))}
      </ol>
      {aside ? (
        <aside className="engineering-flow-aside" aria-label={aside.label}>
          <div className="engineering-flow-label">{aside.label}</div>
          <div className="engineering-flow-value">{aside.value}</div>
        </aside>
      ) : null}
      {explanation ? (
        <p className="engineering-flow-explanation" style={{ margin: 0 }}>
          {explanation}
        </p>
      ) : null}
    </section>
  );
}
