import type { GoldSourceContext as Source } from "../../types";

type Props = {
  source: Source;
  heading?: string;
};

export function GoldSourceContextView({
  source,
  heading = "Source context",
}: Props) {
  const pageRange =
    source.page_start !== null || source.page_end !== null
      ? `pp. ${source.page_start ?? "?"}–${source.page_end ?? "?"}`
      : null;
  const lineRange =
    source.line_start !== null || source.line_end !== null
      ? `lines ${source.line_start ?? "?"}–${source.line_end ?? "?"}`
      : null;

  return (
    <section className="gold-lab-source" aria-labelledby="gold-source-heading">
      <h3 id="gold-source-heading">{heading}</h3>
      <dl className="gold-lab-meta">
        <div>
          <dt>Document</dt>
          <dd>{source.document_title ?? "Untitled document"}</dd>
        </div>
        <div>
          <dt>Source name</dt>
          <dd>{source.source_name ?? "—"}</dd>
        </div>
        <div>
          <dt>Section path</dt>
          <dd>
            {source.section_path.length > 0
              ? source.section_path.join(" / ")
              : "—"}
          </dd>
        </div>
        {pageRange ? (
          <div>
            <dt>Pages</dt>
            <dd>{pageRange}</dd>
          </div>
        ) : null}
        {lineRange ? (
          <div>
            <dt>Lines</dt>
            <dd>{lineRange}</dd>
          </div>
        ) : null}
        <div>
          <dt>Content type</dt>
          <dd>{source.content_type}</dd>
        </div>
      </dl>
      <pre className="gold-lab-source-text">{source.text}</pre>
    </section>
  );
}
