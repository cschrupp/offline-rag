type FlowLayer = {
  title: string;
  detail?: string;
};

type Props = {
  title: string;
  layers: FlowLayer[];
  notes?: string[];
  "data-testid"?: string;
};

/** Accessible layered architecture — visual + semantic ordered list. */
export function ArchitectureFlow({
  title,
  layers,
  notes,
  "data-testid": testId,
}: Props) {
  const headingId = `arch-${title.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;
  return (
    <section
      className="engineering-arch-flow stack"
      aria-labelledby={headingId}
      data-testid={testId}
    >
      <h3 id={headingId} style={{ margin: 0 }}>
        {title}
      </h3>
      <ol className="engineering-arch-layers">
        {layers.map((layer, index) => (
          <li key={layer.title}>
            <div className="engineering-arch-card">
              <div className="engineering-arch-step">Step {index + 1}</div>
              <div className="engineering-arch-title">{layer.title}</div>
              {layer.detail ? (
                <div className="engineering-arch-detail">{layer.detail}</div>
              ) : null}
            </div>
            {index < layers.length - 1 ? (
              <div className="engineering-arch-connector" aria-hidden="true">
                ↓
              </div>
            ) : null}
          </li>
        ))}
      </ol>
      {notes && notes.length > 0 ? (
        <ul className="engineering-arch-notes">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
