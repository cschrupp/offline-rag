import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Badge } from "../components/Badge";
import { Card } from "../components/Card";
import {
  EvidenceManifestError,
  fetchEngineeringEvidenceManifest,
  recordById,
} from "../features/engineering/evidenceClient";
import { ComparisonPanel } from "../features/engineering/ComparisonPanel";
import { EngineeringNav } from "../features/engineering/EngineeringNav";
import { EvidenceMetric } from "../features/engineering/EvidenceMetric";
import { MetricBarChart } from "../features/engineering/MetricBarChart";
import { ProvenanceDetails } from "../features/engineering/ProvenanceDetails";
import { StatusFlow } from "../features/engineering/StatusFlow";
import {
  isMetric,
  type EvidenceRecord,
  type Metric,
} from "../features/engineering/evidenceTypes";

function asMetric(value: unknown): Metric | null {
  return isMetric(value) ? value : null;
}

function PromotionExplain({ badge }: { badge: string }) {
  return (
    <div className="row engineering-status-explain">
      <Badge tone="empty" label={badge} />
      <span>
        Exploratory result; does not authorize a configuration change.
      </span>
    </div>
  );
}

function RetrievalSection({
  record,
  manifestId,
}: {
  record: EvidenceRecord;
  manifestId: string;
}) {
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

  const chartRows =
    population?.arms.map((arm) => ({
      id: arm.arm_id,
      label: `${arm.arm_id} · ${arm.label}`,
      metric: asMetric(arm.metrics.ndcg_at_10)!,
    })) ?? [];

  const takeaway =
    populationId === "human-16"
      ? "Several retrieval variants produce similar top ranking-quality results on this small pilot; ordering of the top two arms changes under the human-16 sensitivity view."
      : "Several retrieval variants produce similar top ranking-quality results on this small pilot; ordering changes under the human-16 sensitivity view.";

  return (
    <Card className="stack engineering-evidence-card">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <div className="row">
          <h2 style={{ margin: 0 }}>Retrieval quality</h2>
          <Badge tone="empty" label="Pilot" />
        </div>
        <PromotionExplain badge="Non-promotional" />
        <p style={{ margin: 0 }}>{record.summary}</p>
        <p className="engineering-result-limit" style={{ margin: 0 }}>
          Exploratory result — does not authorize a configuration change. Small
          descriptive populations only (Slice 9H-P pilot).
        </p>
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
          <p style={{ margin: 0 }}>
            <strong>nDCG@10.</strong> Ranking quality among the first ten
            results; higher is better. This is retrieval-ranking evidence, not
            answer accuracy.
          </p>
          <MetricBarChart
            caption={`Retrieval nDCG@10 — ${population.label} (A–F order preserved)`}
            rows={chartRows}
            domainMax={1}
            valueHeading="nDCG@10"
          />
          <p className="engineering-takeaway" style={{ margin: 0 }}>
            {takeaway}
          </p>
          {population.ndcg_order_note ? (
            <p className="muted" style={{ margin: 0 }}>
              {population.ndcg_order_note}
            </p>
          ) : null}
          <details className="engineering-provenance">
            <summary>View detailed metrics</summary>
            <div className="engineering-table-wrap" style={{ marginTop: "0.75rem" }}>
              <table data-testid="retrieval-metrics-table">
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
                    <tr key={arm.arm_id} data-arm-id={arm.arm_id}>
                      <th scope="row">
                        {arm.arm_id} · {arm.label}
                      </th>
                      <td data-metric="ndcg_at_10">
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
            <p className="muted" style={{ marginTop: "0.75rem" }}>
              Descriptive latency in this table is from the Slice 9H-P pilot
              population and is not interchangeable with Slice 14C or Level-C
              latency measurements.
            </p>
          </details>
        </>
      ) : null}
      <details className="engineering-provenance">
        <summary>Methodological caveats</summary>
        <ul className="engineering-caveats">
          {record.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      </details>
      <ProvenanceDetails record={record} manifestId={manifestId} />
    </Card>
  );
}

function GenerationSection({
  record,
  manifestId,
}: {
  record: EvidenceRecord;
  manifestId: string;
}) {
  const prompts = record.presentation.prompts as
    | Array<{
        prompt_id: string;
        label: string;
        metrics: Record<string, unknown>;
      }>
    | undefined;
  return (
    <Card className="stack engineering-evidence-card">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <div className="row">
          <h2 style={{ margin: 0 }}>Generation &amp; citations</h2>
          <Badge tone="empty" label="Development" />
        </div>
        <PromotionExplain badge="Non-promotional" />
        <p style={{ margin: 0 }}>{record.summary}</p>
        <p className="engineering-result-limit" style={{ margin: 0 }}>
          Development evidence with same-model self-judge limitation. No prompt
          promotion.
        </p>
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
      <details className="engineering-provenance">
        <summary>Methodological caveats</summary>
        <ul className="engineering-caveats">
          {record.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      </details>
      <ProvenanceDetails record={record} manifestId={manifestId} />
    </Card>
  );
}

function Performance14cSection({
  record,
  manifestId,
}: {
  record: EvidenceRecord;
  manifestId: string;
}) {
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
      : "Higher observed ranking quality with higher observed retrieval latency.";

  return (
    <Card className="stack engineering-evidence-card">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>Performance — 14C retrieval quality-vs-cost</h2>
        <PromotionExplain badge="Non-promotional" />
        <p style={{ margin: 0 }}>{record.summary}</p>
        <p className="engineering-result-limit" style={{ margin: 0 }}>
          Separate population from Slice 9H-P descriptive latency and Level-C
          end-to-end measurements. No configuration promotion.
        </p>
      </header>
      {variants ? (
        <>
          <div
            className="engineering-dual-panels"
            data-testid="performance-14c-panels"
          >
            <ComparisonPanel
              title="Quality"
              data-testid="performance-14c-quality"
              variants={variants.map((variant) => ({
                id: variant.variant_id,
                label: variant.label,
                metrics: [
                  {
                    label: "nDCG@10",
                    metric: asMetric(variant.quality.ndcg_at_10)!,
                  },
                ],
              }))}
            />
            <ComparisonPanel
              title="Latency"
              data-testid="performance-14c-latency"
              variants={variants.map((variant) => ({
                id: variant.variant_id,
                label: variant.label,
                metrics: [
                  {
                    label: "Retrieval p50",
                    metric: asMetric(variant.latency.retrieval_p50)!,
                  },
                  {
                    label: "Retrieval p95",
                    metric: asMetric(variant.latency.retrieval_p95)!,
                  },
                ],
              }))}
            />
          </div>
          <p className="engineering-takeaway" style={{ margin: 0 }}>
            Adding the reranker increased observed ranking quality and retrieval
            latency in the accepted 14C benchmark.
          </p>
          <p style={{ margin: 0 }}>{note}</p>
          <details className="engineering-provenance">
            <summary>View detailed metrics</summary>
            <div className="stack" style={{ marginTop: "0.75rem" }}>
              <div className="engineering-table-wrap">
                <table data-testid="performance-14c-quality-table">
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
                      <tr key={`q-${variant.variant_id}`} data-variant-id={variant.variant_id}>
                        <th scope="row">{variant.label}</th>
                        <td data-metric="ndcg_at_10">
                          <EvidenceMetric
                            metric={asMetric(variant.quality.ndcg_at_10)!}
                          />
                        </td>
                        <td>
                          <EvidenceMetric
                            metric={asMetric(variant.quality.hit_at_1)!}
                          />
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
              <div className="engineering-table-wrap">
                <table data-testid="performance-14c-latency-table">
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
                      <tr key={`l-${variant.variant_id}`} data-variant-id={variant.variant_id}>
                        <th scope="row">{variant.label}</th>
                        <td data-metric="retrieval_p50">
                          <EvidenceMetric
                            metric={asMetric(variant.latency.retrieval_p50)!}
                          />
                        </td>
                        <td data-metric="retrieval_p95">
                          <EvidenceMetric
                            metric={asMetric(variant.latency.retrieval_p95)!}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
            </div>
          </details>
        </>
      ) : null}
      <details className="engineering-provenance">
        <summary>Methodological caveats</summary>
        <ul className="engineering-caveats">
          {record.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      </details>
      <ProvenanceDetails record={record} manifestId={manifestId} />
    </Card>
  );
}

function PerformanceLevelCSection({
  record,
  manifestId,
}: {
  record: EvidenceRecord;
  manifestId: string;
}) {
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
    <Card className="stack engineering-evidence-card">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>Performance — Level-C end-to-end</h2>
        <PromotionExplain badge="Non-promotional" />
        <p style={{ margin: 0 }}>{record.summary}</p>
        <p className="engineering-result-limit" style={{ margin: 0 }}>
          Separate population from 14C retrieval-path latency. No derived
          stage-overhead arithmetic.
        </p>
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
      <details className="engineering-provenance">
        <summary>Methodological caveats</summary>
        <ul className="engineering-caveats">
          {record.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      </details>
      <ProvenanceDetails record={record} manifestId={manifestId} />
    </Card>
  );
}

function RecoverySection({
  record,
  manifestId,
}: {
  record: EvidenceRecord;
  manifestId: string;
}) {
  const p = record.presentation;
  return (
    <Card className="stack engineering-evidence-card">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>Recovery</h2>
        <p style={{ margin: 0 }}>{record.summary}</p>
      </header>
      <StatusFlow
        title="Recovery disposition"
        data-testid="recovery-status-flow"
        steps={[
          { label: "Bounded recovery", value: "Implemented" },
          { label: "Evaluation", value: String(p.evaluation) },
          {
            label: "Efficacy evidence",
            value: String(p.efficacy_evidence),
          },
          {
            label: "Product recovery",
            value: String(p.product_recovery),
          },
        ]}
        aside={{
          label: "LangGraph",
          value: String(p.langgraph),
        }}
        explanation="Product recovery remains disabled. This page does not offer a recovery control."
      />
      <details className="engineering-provenance">
        <summary>Methodological caveats</summary>
        <ul className="engineering-caveats">
          {record.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      </details>
      <ProvenanceDetails record={record} manifestId={manifestId} />
    </Card>
  );
}

function SecuritySection({
  record,
  manifestId,
}: {
  record: EvidenceRecord;
  manifestId: string;
}) {
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
    <Card className="stack engineering-evidence-card">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>Security / robustness</h2>
        <p style={{ margin: 0 }}>{record.summary}</p>
        <p className="engineering-result-limit" style={{ margin: 0 }}>
          Campaign execution completed is not a campaign PASS. Campaign FAIL is
          not a harness implementation failure.
        </p>
      </header>
      {primary ? (
        <StatusFlow
          title="Security campaign disposition"
          data-testid="security-status-flow"
          steps={[
            { label: "Campaign execution", value: primary.execution },
            {
              label: "Required invariant",
              value: "security_policy_immutable_v1 — Unevaluable",
            },
            {
              label: "Fail-closed contract",
              value: primary.campaign_outcome,
            },
          ]}
          aside={{
            label: "Harness implementation",
            value: primary.harness_implementation,
          }}
          explanation="The campaign completed, but one required invariant could not be evaluated on the accepted measurement surface. The campaign therefore fails closed by contract. Harness accepted does not mean security passed."
        />
      ) : null}
      {cohort ? (
        <details className="engineering-provenance">
          <summary>View cohort detail</summary>
          <div className="stack" style={{ marginTop: "0.75rem" }}>
            <p className="muted" style={{ margin: 0 }}>
              {cohort.note}
            </p>
            <p style={{ margin: 0 }}>
              Adversarial evaluator outcomes: pass {cohort.adversarial.pass} /
              fail {cohort.adversarial.fail}
            </p>
            <p style={{ margin: 0 }}>
              Benign evaluator outcomes: pass {cohort.benign.pass} / fail{" "}
              {cohort.benign.fail}; false positives{" "}
              {cohort.benign.false_positives}
            </p>
          </div>
        </details>
      ) : null}
      <details className="engineering-provenance">
        <summary>Methodological caveats</summary>
        <ul className="engineering-caveats">
          {record.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      </details>
      <ProvenanceDetails record={record} manifestId={manifestId} />
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
        {retrieval ? (
          <RetrievalSection
            record={retrieval}
            manifestId={manifest.manifest_id}
          />
        ) : null}
        {generation ? (
          <GenerationSection
            record={generation}
            manifestId={manifest.manifest_id}
          />
        ) : null}
        {perf14c ? (
          <Performance14cSection
            record={perf14c}
            manifestId={manifest.manifest_id}
          />
        ) : null}
        {levelC ? (
          <PerformanceLevelCSection
            record={levelC}
            manifestId={manifest.manifest_id}
          />
        ) : null}
        {recovery ? (
          <RecoverySection
            record={recovery}
            manifestId={manifest.manifest_id}
          />
        ) : null}
        {security ? (
          <SecuritySection
            record={security}
            manifestId={manifest.manifest_id}
          />
        ) : null}
      </div>
    );
  }, [query.data, query.error, query.isError, query.isLoading]);

  return (
    <div className="stack engineering-page">
      <header className="stack engineering-page-header" style={{ gap: "0.5rem" }}>
        <h1>Engineering evidence</h1>
        <p style={{ margin: 0 }}>
          Accepted project evaluation evidence for inspection and demo — not live
          telemetry and not an experiment console.
        </p>
        <ul className="engineering-page-limits">
          <li>Static accepted evidence</li>
          <li>Read-only</li>
          <li>No live benchmark execution</li>
        </ul>
        <EngineeringNav />
      </header>
      {content}
    </div>
  );
}
