import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import {
  EvidenceManifestError,
  fetchEngineeringEvidenceManifest,
} from "../features/engineering/evidenceClient";
import { EngineeringNav } from "../features/engineering/EngineeringNav";
import { EvidenceMetric } from "../features/engineering/EvidenceMetric";
import { MetricBarChart } from "../features/engineering/MetricBarChart";
import {
  PortfolioProjectionError,
  projectEngineeringSummary,
} from "../features/engineering/portfolioProjection";
import type { Metric } from "../features/engineering/evidenceTypes";

function EvidenceLink({ evidenceId, children = "Inspect evidence" }: {
  evidenceId: string;
  children?: string;
}) {
  return <Link to={`/engineering/evidence#evidence-${evidenceId}`}>{children}</Link>;
}

function Measurement({ label, metric }: { label: string; metric: Metric }) {
  return (
    <div className="engineering-summary-measurement">
      <dt>{label}</dt>
      <dd><EvidenceMetric metric={metric} /></dd>
    </div>
  );
}

export function EngineeringSummaryPage() {
  const query = useQuery({
    queryKey: ["engineering-evidence-manifest"],
    queryFn: ({ signal }) => fetchEngineeringEvidenceManifest(signal),
  });

  let summaryProjection: ReturnType<typeof projectEngineeringSummary> | undefined;
  let projectionError: unknown;
  if (query.data && !query.isError) {
    try {
      summaryProjection = projectEngineeringSummary(query.data);
    } catch (error) {
      projectionError = error;
    }
  }

  let content;
  if (query.isLoading) {
    content = <p className="muted">Loading Engineering summary…</p>;
  } else if (query.isError || !query.data) {
    const message =
      query.error instanceof EvidenceManifestError
        ? query.error.message
        : "The bundled evidence manifest could not be validated.";
    content = (
      <p className="error-box" role="alert">
        Engineering summary is unavailable because its evidence could not be
        loaded and validated.
        <br />
        <span className="muted">{message}</span>
      </p>
    );
  } else if (projectionError || !summaryProjection) {
    const message =
      projectionError instanceof PortfolioProjectionError
        ? projectionError.message
        : "A required semantic evidence binding is invalid.";
    content = (
      <p className="error-box" role="alert">
        Engineering summary is unavailable. {message}
      </p>
    );
  } else {
      const summary = summaryProjection;
      const answered = summary.generation.answered.value;
      const total = summary.generation.population.value;
      const failures = summary.generation.failures.value;
      const grade2Hits = summary.generation.grade2Hits.value;
      const grade2Eligible = summary.generation.grade2Eligible.value;
      content = (
        <div className="stack engineering-summary" data-testid="engineering-summary">
          <Card className="stack" id="what-seneca-does">
            <h2>Ask technical documents a question and get an answer you can inspect.</h2>
            <p>
              Seneca answers questions about technical documents on your machine.
              It reads PDFs, finds relevant passages and writes answers with
              citations. After setup, document processing, retrieval and
              generation stay local by default. An operator may send only
              answer-writing to an approved external model.
            </p>
            <ol className="engineering-summary-process" aria-label="How a grounded answer is produced">
              <li>Read and index the documents</li>
              <li>Search by keyword and by meaning</li>
              <li>Merge results and re-rank them</li>
              <li>Write an answer from the top passages</li>
              <li>Check every citation against those passages</li>
            </ol>
            <p className="muted">
              The citation check confirms that each citation points to a passage
              retrieved for that question. It does not judge whether the passage
              supports the sentence.
            </p>
            <p className="muted">
              <strong>Built with:</strong> FastAPI · React · Docling · Qdrant Local ·
              Qwen3-Embedding-0.6B · bge-reranker-v2-m3 · Ollama
            </p>
            <EvidenceLink evidenceId={summary.evidence.citationId}>How the citation check works</EvidenceLink>
          </Card>

          <Card className="stack" id="finding-passages">
            <h2>Re-ranking improved search quality, at a cost in speed.</h2>
            <p>
              Ranking quality (nDCG@10) scores how well relevant passages rank in
              the first ten results, from 0 to 1. It measures search, not answer accuracy.
            </p>
            <div className="engineering-table-wrap">
              <table>
                <caption>Search quality and median search time</caption>
                <thead><tr><th scope="col">Measure</th><th scope="col">Keyword + meaning</th><th scope="col">With re-ranking</th></tr></thead>
                <tbody>
                  <tr>
                    <th scope="row">Ranking quality</th>
                    <td><EvidenceMetric metric={summary.retrieval.hybridQuality} /></td>
                    <td><EvidenceMetric metric={summary.retrieval.rerankedQuality} /></td>
                  </tr>
                  <tr>
                    <th scope="row">Median search time</th>
                    <td><EvidenceMetric metric={summary.retrieval.hybridLatency} /></td>
                    <td><EvidenceMetric metric={summary.retrieval.rerankedLatency} /></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <MetricBarChart
              caption="Ranking quality on a scale from 0 to 1"
              rows={[
                { id: "keyword-meaning", label: "Keyword + meaning", metric: summary.retrieval.hybridQuality },
                { id: "with-reranking", label: "With re-ranking", metric: summary.retrieval.rerankedQuality },
              ]}
              domainMax={1}
              valueHeading="Ranking quality"
            />
            <p>
              Re-ranking raised quality from{" "}
              <EvidenceMetric metric={summary.retrieval.hybridQuality} /> to{" "}
              <EvidenceMetric metric={summary.retrieval.rerankedQuality} /> and
              median search time from{" "}
              <EvidenceMetric metric={summary.retrieval.hybridLatency} /> to{" "}
              <EvidenceMetric metric={summary.retrieval.rerankedLatency} />.
            </p>
            <p className="muted">
              Keyword search stays alongside meaning-based search because exact
              identifiers, codes and names are reliably found by keywords.
            </p>
            <p className="muted">
              Two meaning-only variants scored slightly higher in a small pilot (
              <EvidenceMetric metric={summary.retrieval.densePilotC} /> and{" "}
              <EvidenceMetric metric={summary.retrieval.densePilotD} />), and
              their order reversed on human-graded questions. This small test
              cannot separate results that close, so no variant is claimed as best.
            </p>
            <p className="muted">
              <strong>How measured.</strong> Development benchmark on{" "}
              {summary.retrieval.cpuModel}{" "}with {summary.retrieval.embeddingModel} and{" "}
              {summary.retrieval.rerankerModel}.
              Timings are not a speed target.
            </p>
            <EvidenceLink evidenceId={summary.evidence.retrievalId}>Inspect the retrieval evidence</EvidenceLink>
          </Card>

          <Card className="stack" id="answers-you-can-check">
            <h2>
              Seneca answered {answered} of {total} test questions, and{" "}
              {summary.generation.noInvalidCitations
                ? "no answer cited a passage outside its retrieved set."
                : "some answers cited a passage outside their retrieved set."}
            </h2>
            <dl className="engineering-summary-measurements">
              <div className="engineering-summary-measurement">
                <dt>Questions answered</dt>
                <dd>{answered} of {total}<span><EvidenceMetric metric={summary.generation.answerRate} /></span></dd>
              </div>
              <div className="engineering-summary-measurement">
                <dt>Failed to generate</dt>
                <dd>{failures} of {total}<span><EvidenceMetric metric={summary.generation.failureRate} /></span></dd>
              </div>
              <div className="engineering-summary-measurement">
                <dt>Answers citing a top-rated passage</dt>
                <dd>{grade2Hits} of {grade2Eligible}<span><EvidenceMetric metric={summary.generation.grade2Rate} /></span></dd>
              </div>
              <Measurement label="Invalid citations" metric={summary.generation.invalidCitationRate} />
            </dl>
            <p>
              The {failures} unanswered questions failed during generation and
              were reported as failures, not answers. The third tile covers the{" "}
              {grade2Eligible} answered questions that had a top-rated reference
              passage; {grade2Hits} cited one.
            </p>
            <p className="muted">
              Answer quality was graded by the same model that wrote the answers.
              Those grades are a development signal, so they are not shown on this
              page.
            </p>
            <p className="muted">
              <strong>How measured.</strong> {total} development questions; answers
              were written by the local {summary.generation.generatorModel} model.
            </p>
            <EvidenceLink evidenceId={summary.evidence.generationCountsId}>Inspect the answer evidence</EvidenceLink>
          </Card>

          <Card className="stack" id="local-execution">
            <h2>Seneca runs on a CPU alone, and uses an NVIDIA GPU when one is available.</h2>
            <p>
              The search model has CPU and half-precision NVIDIA GPU paths. Seneca
              detects hardware and selects a supported path automatically. Both
              paths have been qualified on real installations.
            </p>
            <div className="engineering-summary-two-column">
              <div><h3>Largest PDF accepted</h3><p><EvidenceMetric metric={summary.capacity.pdfLimit} /></p></div>
              <div><h3>Extra checks above</h3><p><EvidenceMetric metric={summary.capacity.threshold} /></p>
                <p className="muted">Before accepting a larger PDF, Seneca checks available memory and disk space.</p>
              </div>
            </div>
            <h3>CPU container image size</h3>
            <div className="engineering-table-wrap">
              <table>
                <caption className="visually-hidden">CPU container image sizes before and after optimization</caption>
                <thead><tr><th scope="col">Stage</th><th scope="col">Image size</th></tr></thead>
                <tbody>
                  <tr><th scope="row">Before</th><td><EvidenceMetric metric={summary.images.original} /></td></tr>
                  <tr><th scope="row">After</th><td><EvidenceMetric metric={summary.images.optimized} /></td></tr>
                  <tr><th scope="row">Reduction</th><td><EvidenceMetric metric={summary.images.reduction} /></td></tr>
                </tbody>
              </table>
            </div>
            <p>
              The CPU release image was reduced from{" "}
              <EvidenceMetric metric={summary.images.original} /> to{" "}
              <EvidenceMetric metric={summary.images.optimized} />, a{" "}
              <EvidenceMetric metric={summary.images.reduction} /> reduction.
            </p>
            <p className="muted">
              Removing the CUDA/GPU dependencies was a major contributor; the
              packaging test also changed other dependencies and build steps.
            </p>
            <details>
              <summary>How long does a full answer take?</summary>
              <p>
                With a large local model, a full question took a median of{" "}
                <EvidenceMetric metric={summary.levelC.endToEndP50} />; answer writing
                alone took <EvidenceMetric metric={summary.levelC.generationP50} />.
                One machine and model were measured over {summary.levelC.cases} questions
                and {summary.levelC.measured} runs. This is not a speed target; search
                time in Section 2 was measured separately.
              </p>
              <EvidenceLink evidenceId="performance.slice14-level-c">Inspect the runtime evidence</EvidenceLink>
            </details>
          </Card>

          <Card className="stack" id="not-shipped">
            <h2>Test results decided what shipped: two features were held back, and one security test is still open.</h2>
            <div className="engineering-summary-story">
              <h3>Free-text conversation routing</h3>
              <p><strong>Rejected</strong></p>
              <p>
                A model routed typed requests around document search. The rule
                prohibited this for factual questions, but an unseen Spanish
                request combined a rewrite with a factual question and bypassed
                search. Seneca rejected the router and offers Summarize, Simplify
                and Translate as explicit actions. Factual questions still use search.
              </p>
            </div>
            <div className="engineering-summary-story">
              <h3>Automatic query retry</h3>
              <p><strong>Built, switched off</strong></p>
              <p>
                When results are weak, Seneca can rewrite the question and retry.
                It was built and tested, but did not show enough benefit, so it remains off.
              </p>
            </div>
            <div className="engineering-summary-story">
              <h3>Adversarial security test</h3>
              <p><strong>Open</strong></p>
              <p>
                An attack campaign tested question-answering. One required check
                could not run, which the rules count as a failure. The campaign is
                marked failed. This does not show attacks succeeded or establish
                that Seneca is secure.
              </p>
            </div>
            <p className="engineering-takeaway">Code ships only when it meets the rule set before testing.</p>
            <EvidenceLink evidenceId={summary.evidence.decisionsId}>Inspect the decision evidence</EvidenceLink>
          </Card>

          <Card className="stack" id="verify-claims">
            <h2>Every number on this page can be traced to its source.</h2>
            <p>
              The numbers above are read from a versioned evidence file rather
              than typed into the page. For each result, the Evidence page shows
              the test set, exact stored value and source file with its checksum.
              Missing or invalid evidence produces an error, never substituted
              numbers.
            </p>
            <div className="row">
              <Button to="/engineering/evidence" variant="primary">Inspect the evidence</Button>
              <Button to="/engineering/architecture" variant="secondary">See the architecture</Button>
              <a className="btn btn-secondary" href="https://github.com/cschrupp/offline-rag" target="_blank" rel="noreferrer">View source</a>
            </div>
          </Card>
        </div>
      );
  }

  return (
    <div className="stack engineering-page">
      <header className="stack engineering-page-header" style={{ gap: "0.5rem" }}>
        <h1>Engineering</h1>
        <p style={{ margin: 0 }}>
          What Seneca does, how well it worked in testing, what was left out, and
          how to check each claim.
        </p>
        <EngineeringNav />
      </header>
      {content}
    </div>
  );
}
