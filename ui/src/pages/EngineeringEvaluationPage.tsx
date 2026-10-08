import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Badge } from "../components/Badge";
import { Card } from "../components/Card";
import {
  EvidenceManifestError,
  fetchEngineeringEvidenceManifest,
  recordById,
} from "../features/engineering/evidenceClient";
import { EngineeringNav } from "../features/engineering/EngineeringNav";
import { EvidenceMetric } from "../features/engineering/EvidenceMetric";
import { ProvenanceDetails } from "../features/engineering/ProvenanceDetails";
import {
  isMetric,
  type EvidenceRecord,
  type Metric,
} from "../features/engineering/evidenceTypes";

function asMetric(value: unknown): Metric | null {
  return isMetric(value) ? value : null;
}

function CaveatList({ record }: { record: EvidenceRecord }) {
  return (
    <ul className="engineering-caveats">
      {record.caveats.map((caveat) => (
        <li key={caveat}>{caveat}</li>
      ))}
    </ul>
  );
}

function RetrievalSection({ record }: { record: EvidenceRecord }) {
  const presentation = record.presentation;
  const populations = presentation.populations as
    | Record<
        string,
        {
          label: string;
          ndcg_order_note?: string;
          arms: Array<{
            arm_id: string;
            label: string;
            metrics: Record<string, unknown>;
          }>;
        }
      >
    | undefined;
  const populationIds = populations ? Object.keys(populations) : [];
  const defaultPopulation =
    typeof presentation.default_population === "string"
      ? presentation.default_population
      : populationIds[0];
  const [populationId, setPopulationId] = useState(defaultPopulation ?? "");
  const population = populations?.[populationId];

  return (
    <Card className="stack">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <div className="row">
          <h2 style={{ margin: 0 }}>Retrieval quality</h2>
          <Badge tone="empty" label="Pilot" />
          <Badge tone="empty" label="Non-promotional" />
        </div>
        <p className="muted" style={{ margin: 0 }}>
          {record.summary}
        </p>
        <CaveatList record={record} />
      </header>
      {populationIds.length > 1 ? (
        <div className="row">
          <label htmlFor="retrieval-population">
            Population
            <select
              id="retrieval-population"
              value={populationId}
              onChange={(event) => setPopulationId(event.target.value)}
            >
              {populationIds.map((id) => (
                <option key={id} value={id}>
                  {populations?.[id]?.label ?? id}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
      {population ? (
        <>
          <p className="muted" style={{ margin: 0 }}>
            {population.ndcg_order_note}
          </p>
          <div className="engineering-table-wrap">
            <table>
              <caption>
                Retrieval arms for {population.label} (static accepted evidence)
              </caption>
              <thead>
                <tr>
                  <th scope="col">Arm</th>
                  <th scope="col">nDCG@10</th>
                  <th scope="col">Hit@1</th>
                  <th scope="col">MRR</th>
                  <th scope="col">Recall@10</th>
                  <th scope="col">Descriptive latency</th>
                </tr>
              </thead>
              <tbody>
                {population.arms.map((arm) => (
                  <tr key={arm.arm_id}>
                    <th scope="row">
                      {arm.arm_id} · {arm.label}
                    </th>
                    <td>
                      <EvidenceMetric metric={asMetric(arm.metrics.ndcg_at_10)!} />
                    </td>
                    <td>
                      <EvidenceMetric metric={asMetric(arm.metrics.hit_at_1)!} />
                    </td>
                    <td>
                      <EvidenceMetric metric={asMetric(arm.metrics.mrr)!} />
                    </td>
                    <td>
                      <EvidenceMetric
                        metric={asMetric(arm.metrics.recall_at_10)!}
                      />
                    </td>
                    <td>
                      <EvidenceMetric
                        metric={asMetric(arm.metrics.descriptive_latency)!}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
      <ProvenanceDetails record={record} />
    </Card>
  );
}

function GenerationSection({ record }: { record: EvidenceRecord }) {
  const prompts = record.presentation.prompts as
    | Array<{
        prompt_id: string;
        label: string;
        metrics: Record<string, unknown>;
      }>
    | undefined;
  return (
    <Card className="stack">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <div className="row">
          <h2 style={{ margin: 0 }}>Generation &amp; citations</h2>
          <Badge tone="empty" label="Development" />
          <Badge tone="empty" label="Non-promotional" />
        </div>
        <p className="muted" style={{ margin: 0 }}>
          {record.summary}
        </p>
        <CaveatList record={record} />
      </header>
      {prompts ? (
        <div className="engineering-table-wrap">
          <table>
            <caption>Selected Slice 10E positive full-22 metrics</caption>
            <thead>
              <tr>
                <th scope="col">Prompt</th>
                <th scope="col">Answer rate</th>
                <th scope="col">Generation failure</th>
                <th scope="col">Citation invalid</th>
                <th scope="col">Mean gold citation recall</th>
                <th scope="col">Grade-2 citation hit</th>
                <th scope="col">Fully correct</th>
              </tr>
            </thead>
            <tbody>
              {prompts.map((prompt) => (
                <tr key={prompt.prompt_id}>
                  <th scope="row">{prompt.label}</th>
                  <td>
                    <EvidenceMetric metric={asMetric(prompt.metrics.answer_rate)!} />
                  </td>
                  <td>
                    <EvidenceMetric
                      metric={asMetric(prompt.metrics.generation_failed_rate)!}
                    />
                  </td>
                  <td>
                    <EvidenceMetric
                      metric={asMetric(prompt.metrics.citation_invalid_rate)!}
                    />
                  </td>
                  <td>
                    <EvidenceMetric
                      metric={asMetric(prompt.metrics.mean_gold_citation_recall)!}
                    />
                  </td>
                  <td>
                    <EvidenceMetric
                      metric={asMetric(prompt.metrics.grade2_citation_hit_rate)!}
                    />
                  </td>
                  <td>
                    <EvidenceMetric
                      metric={asMetric(prompt.metrics.fully_correct_rate)!}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <ProvenanceDetails record={record} />
    </Card>
  );
}

function Performance14cSection({ record }: { record: EvidenceRecord }) {
  const variants = record.presentation.variants as
    | Array<{
        variant_id: string;
        label: string;
        quality: Record<string, unknown>;
        latency: Record<string, unknown>;
        resources: Record<string, unknown>;
      }>
    | undefined;
  const note =
    typeof record.presentation.comparison_note === "string"
      ? record.presentation.comparison_note
      : null;
  return (
    <Card className="stack">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>Performance — 14C retrieval quality-vs-cost</h2>
        <p className="muted" style={{ margin: 0 }}>
          {record.summary}
        </p>
        <CaveatList record={record} />
        {note ? <p style={{ margin: 0 }}>{note}</p> : null}
      </header>
      {variants ? (
        <>
          <h3>Quality</h3>
          <div className="engineering-table-wrap">
            <table>
              <caption>14C quality metrics by variant</caption>
              <thead>
                <tr>
                  <th scope="col">Variant</th>
                  <th scope="col">nDCG@10</th>
                  <th scope="col">Hit@1</th>
                  <th scope="col">MRR</th>
                  <th scope="col">Recall@10</th>
                </tr>
              </thead>
              <tbody>
                {variants.map((variant) => (
                  <tr key={`q-${variant.variant_id}`}>
                    <th scope="row">{variant.label}</th>
                    <td>
                      <EvidenceMetric metric={asMetric(variant.quality.ndcg_at_10)!} />
                    </td>
                    <td>
                      <EvidenceMetric metric={asMetric(variant.quality.hit_at_1)!} />
                    </td>
                    <td>
                      <EvidenceMetric metric={asMetric(variant.quality.mrr)!} />
                    </td>
                    <td>
                      <EvidenceMetric
                        metric={asMetric(variant.quality.recall_at_10)!}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Latency</h3>
          <div className="engineering-table-wrap">
            <table>
              <caption>14C retrieval-path latency by variant</caption>
              <thead>
                <tr>
                  <th scope="col">Variant</th>
                  <th scope="col">Retrieval p50</th>
                  <th scope="col">Retrieval p95</th>
                </tr>
              </thead>
              <tbody>
                {variants.map((variant) => (
                  <tr key={`l-${variant.variant_id}`}>
                    <th scope="row">{variant.label}</th>
                    <td>
                      <EvidenceMetric
                        metric={asMetric(variant.latency.retrieval_p50)!}
                      />
                    </td>
                    <td>
                      <EvidenceMetric
                        metric={asMetric(variant.latency.retrieval_p95)!}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Resources</h3>
          <div className="engineering-table-wrap">
            <table>
              <caption>14C resource observations by variant</caption>
              <thead>
                <tr>
                  <th scope="col">Variant</th>
                  <th scope="col">RAM RSS p50</th>
                  <th scope="col">VRAM availability</th>
                </tr>
              </thead>
              <tbody>
                {variants.map((variant) => (
                  <tr key={`r-${variant.variant_id}`}>
                    <th scope="row">{variant.label}</th>
                    <td>
                      <EvidenceMetric
                        metric={asMetric(variant.resources.ram_rss_bytes_p50)!}
                      />
                    </td>
                    <td>
                      <EvidenceMetric
                        metric={asMetric(variant.resources.vram_availability)!}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
      <ProvenanceDetails record={record} />
    </Card>
  );
}

function PerformanceLevelCSection({ record }: { record: EvidenceRecord }) {
  const metrics = record.presentation.metrics as Record<string, unknown> | undefined;
  const rows: Array<[string, string]> = [
    ["End-to-end p50", "end_to_end_p50"],
    ["End-to-end p95", "end_to_end_p95"],
    ["Generation p50", "generation_p50"],
    ["Generation p95", "generation_p95"],
    ["TTFT", "ttft"],
    ["Decode latency", "decode_latency"],
    ["Tokens/sec", "tokens_per_sec"],
  ];
  return (
    <Card className="stack">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>Performance — Level-C end-to-end</h2>
        <p className="muted" style={{ margin: 0 }}>
          {record.summary}
        </p>
        <CaveatList record={record} />
      </header>
      {metrics ? (
        <div className="engineering-table-wrap">
          <table>
            <caption>Level-C end-to-end generation-path metrics</caption>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Value</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([label, key]) => {
                const metric = asMetric(metrics[key]);
                return (
                  <tr key={key}>
                    <th scope="row">{label}</th>
                    <td>
                      {metric ? <EvidenceMetric metric={metric} /> : "Unavailable"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      <ProvenanceDetails record={record} />
    </Card>
  );
}

function RecoverySection({ record }: { record: EvidenceRecord }) {
  const p = record.presentation;
  return (
    <Card className="stack">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>Recovery</h2>
        <p className="muted" style={{ margin: 0 }}>
          {record.summary}
        </p>
        <CaveatList record={record} />
      </header>
      <dl className="engineering-status-dl">
        <div>
          <dt>Evaluation</dt>
          <dd>{String(p.evaluation)}</dd>
        </div>
        <div>
          <dt>Efficacy evidence</dt>
          <dd>{String(p.efficacy_evidence)}</dd>
        </div>
        <div>
          <dt>Product recovery</dt>
          <dd>{String(p.product_recovery)}</dd>
        </div>
        <div>
          <dt>LangGraph</dt>
          <dd>{String(p.langgraph)}</dd>
        </div>
      </dl>
      <ProvenanceDetails record={record} />
    </Card>
  );
}

function SecuritySection({ record }: { record: EvidenceRecord }) {
  const primary = record.presentation.primary as
    | {
        title: string;
        execution: string;
        campaign_outcome: string;
        interpretation: string;
        harness_implementation: string;
      }
    | undefined;
  const cohort = record.presentation.cohort_detail as
    | {
        adversarial: { pass: number; fail: number };
        benign: { pass: number; fail: number; false_positives: number };
        note: string;
      }
    | undefined;
  return (
    <Card className="stack">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>Security / robustness</h2>
        <p className="muted" style={{ margin: 0 }}>
          {record.summary}
        </p>
        <CaveatList record={record} />
      </header>
      {primary ? (
        <dl className="engineering-status-dl">
          <div>
            <dt>Campaign</dt>
            <dd>{primary.title}</dd>
          </div>
          <div>
            <dt>Execution</dt>
            <dd>{primary.execution}</dd>
          </div>
          <div>
            <dt>Campaign outcome</dt>
            <dd>{primary.campaign_outcome}</dd>
          </div>
          <div>
            <dt>Interpretation</dt>
            <dd>{primary.interpretation}</dd>
          </div>
          <div>
            <dt>Harness</dt>
            <dd>{primary.harness_implementation}</dd>
          </div>
        </dl>
      ) : null}
      {cohort ? (
        <details className="engineering-provenance">
          <summary>View cohort detail</summary>
          <div className="stack" style={{ marginTop: "0.75rem" }}>
            <p className="muted" style={{ margin: 0 }}>
              {cohort.note}
            </p>
            <p style={{ margin: 0 }}>
              Adversarial evaluator outcomes: pass {cohort.adversarial.pass} / fail{" "}
              {cohort.adversarial.fail}
            </p>
            <p style={{ margin: 0 }}>
              Benign evaluator outcomes: pass {cohort.benign.pass} / fail{" "}
              {cohort.benign.fail}; false positives {cohort.benign.false_positives}
            </p>
          </div>
        </details>
      ) : null}
      <ProvenanceDetails record={record} />
    </Card>
  );
}

export function EngineeringEvaluationPage() {
  const query = useQuery({
    queryKey: ["engineering-evidence-manifest"],
    queryFn: ({ signal }) => fetchEngineeringEvidenceManifest(signal),
  });

  const content = useMemo(() => {
    if (query.isLoading) {
      return <p className="muted">Loading engineering evidence…</p>;
    }
    if (query.isError || !query.data) {
      const message =
        query.error instanceof EvidenceManifestError
          ? query.error.message
          : "Engineering evidence is unavailable.";
      return (
        <p className="error-box" role="alert">
          Engineering evidence is unavailable.
          <br />
          The bundled evidence manifest could not be validated.
          <br />
          <span className="muted">{message}</span>
        </p>
      );
    }
    const manifest = query.data;
    const retrieval = recordById(manifest, "retrieval.slice9hp");
    const generation = recordById(manifest, "generation.slice10e");
    const perf14c = recordById(manifest, "performance.slice14c");
    const levelC = recordById(manifest, "performance.slice14-level-c");
    const recovery = recordById(manifest, "recovery.slice12c");
    const security = recordById(manifest, "security.slice13b");
    return (
      <div className="stack">
        <p className="muted" style={{ margin: 0 }}>
          Manifest <code>{manifest.manifest_id}</code>. Static accepted evidence
          only — not live telemetry and not an experiment console.
        </p>
        {retrieval ? <RetrievalSection record={retrieval} /> : null}
        {generation ? <GenerationSection record={generation} /> : null}
        {perf14c ? <Performance14cSection record={perf14c} /> : null}
        {levelC ? <PerformanceLevelCSection record={levelC} /> : null}
        {recovery ? <RecoverySection record={recovery} /> : null}
        {security ? <SecuritySection record={security} /> : null}
      </div>
    );
  }, [query.data, query.error, query.isError, query.isLoading]);

  return (
    <div className="stack engineering-page">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h1>Engineering evidence</h1>
        <p className="muted" style={{ margin: 0 }}>
          Read-only presentation of accepted evaluation evidence. Seneca does not
          execute benchmarks or mutate scientific configuration from this page.
        </p>
        <EngineeringNav />
      </header>
      {content}
    </div>
  );
}
