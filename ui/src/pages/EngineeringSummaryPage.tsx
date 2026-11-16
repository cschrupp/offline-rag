import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Card } from "../components/Card";
import {
  EvidenceManifestError,
  fetchEngineeringEvidenceManifest,
} from "../features/engineering/evidenceClient";
import { EngineeringNav } from "../features/engineering/EngineeringNav";
import { EvidenceMetric } from "../features/engineering/EvidenceMetric";
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

function comparisonDirection(candidate: Metric, baseline: Metric): string {
  if (candidate.value === null || baseline.value === null) return "unavailable";
  if (candidate.value > baseline.value) return "higher";
  if (candidate.value < baseline.value) return "lower";
  return "the same";
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
      const qualityDirection = comparisonDirection(
        summary.retrieval.rerankedQuality,
        summary.retrieval.hybridQuality,
      );
      const latencyDirection = comparisonDirection(
        summary.retrieval.rerankedLatency,
        summary.retrieval.hybridLatency,
      );
      content = (
        <div className="stack engineering-summary" data-testid="engineering-summary">
          <Card className="stack" id="what-seneca-does">
            <h2>Ask technical documents a question and get an answer you can inspect.</h2>
            <p>
              Seneca is a local-first knowledge workspace. It parses and indexes
              technical documents, finds relevant passages through semantic and
              lexical retrieval, reranks candidates, and generates a cited answer.
              Standalone operation is local and strict-offline by default; an
              operator may separately configure an approved optional external
              generation endpoint.
            </p>
            <ol className="engineering-summary-process" aria-label="How a grounded answer is produced">
              <li>Technical documents</li>
              <li>Retrieve relevant passages</li>
              <li>Fuse candidates and rerank evidence</li>
              <li>Generate an answer from the selected context</li>
              <li>Check citation membership and resolve source provenance</li>
            </ol>
            <p className="muted">
              {summary.generation.citationMembershipClaim}
            </p>
            <p className="muted">
              <strong>How measured.</strong> This describes the accepted
              request/evidence path; the citation check confirms membership and
              provenance, not semantic entailment or faithfulness.
            </p>
            <EvidenceLink evidenceId={summary.evidence.citationId} />
            <EvidenceLink evidenceId={summary.evidence.configId}>Inspect configuration evidence</EvidenceLink>
          </Card>

          <Card className="stack" id="finding-passages">
            <h2>Reranking improved observed retrieval quality, with additional latency.</h2>
            <p>
              nDCG@10 describes how relevant passages are ordered among the
              first ten results. Higher values indicate better observed ranking;
              this is a retrieval measure, not answer accuracy.
            </p>
            <div className="engineering-table-wrap">
              <table>
                <caption>Recorded development retrieval comparison</caption>
                <thead>
                  <tr><th scope="col">Measure</th><th scope="col">Hybrid</th><th scope="col">Hybrid + reranker</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">nDCG@10</th>
                    <td><EvidenceMetric metric={summary.retrieval.hybridQuality} /></td>
                    <td><EvidenceMetric metric={summary.retrieval.rerankedQuality} /></td>
                  </tr>
                  <tr>
                    <th scope="row">Retrieval p50</th>
                    <td><EvidenceMetric metric={summary.retrieval.hybridLatency} /></td>
                    <td><EvidenceMetric metric={summary.retrieval.rerankedLatency} /></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p>
              In this recorded comparison, reranking produced {qualityDirection}
              observed ranking quality and {latencyDirection} retrieval latency.
              Technical documents
              often benefit from both lexical matching of exact terms and
              semantic search for related wording. Keeping reranking separate
              lets candidate retrieval and cross-encoder ranking be measured
              independently.
            </p>
            <p className="muted">
              A separate small pilot recorded dense-only variants at{" "}
              <EvidenceMetric metric={summary.retrieval.densePilotC} /> and{" "}
              <EvidenceMetric metric={summary.retrieval.densePilotD} /> nDCG@10.
              The top two dense variants changed order on the human-only
              sensitivity population.
              These small experiments did not establish a universal production
              winner. Semantic and lexical retrieval remain complementary
              candidate sources under the technical-document rationale.
            </p>
            <p className="muted"><strong>How measured.</strong> The primary comparison comes from the accepted development retrieval population. Dense values come from a separate small retrieval pilot.</p>
            <EvidenceLink evidenceId={summary.evidence.retrievalId} />
            <EvidenceLink evidenceId={summary.evidence.pilotId}>Inspect dense pilot</EvidenceLink>
          </Card>

          <Card className="stack" id="answers-you-can-check">
            <h2>
              Seneca answered {answered} of {total} development questions;{" "}
              {summary.generation.noInvalidCitations
                ? "citation membership validation recorded no invalid citation IDs."
                : "the reported invalid-citation rate was nonzero."}
            </h2>
            <dl className="engineering-summary-measurements">
              <Measurement label={`${answered} of ${total} questions answered`} metric={summary.generation.answerRate} />
              <Measurement label={`${failures} of ${total} generation failures`} metric={summary.generation.failureRate} />
              <Measurement label={`${grade2Hits} of ${grade2Eligible} top-grade citation hits`} metric={summary.generation.grade2Rate} />
              <Measurement label="Invalid citation rate" metric={summary.generation.invalidCitationRate} />
            </dl>
            <p>{failures} unanswered cases were generation failures, not model abstentions.</p>
            <p className="muted">
              This was a development fixture. The generator and judge used the
              same model and endpoint, so self-judge results are not independent
              accuracy evidence. Citation membership validation does not prove
              that cited passages semantically support every generated claim.
            </p>
            <p className="muted"><strong>How measured.</strong> Counts and rates are reported for the positive development population; grade-2 citation hits use the explicitly reported eligible subset.</p>
            <EvidenceLink evidenceId={summary.evidence.generationCountsId} />
            <EvidenceLink evidenceId={summary.evidence.generationId}>Inspect prompt comparison</EvidenceLink>
          </Card>

          <Card className="stack" id="local-execution">
            <h2>Local execution works across CPU and compatible NVIDIA GPU systems.</h2>
            <p>{summary.runtime.currentProfilesClaim}</p>
            <div className="engineering-summary-two-column">
              <div><h3>Current PDF product limit</h3><p><EvidenceMetric metric={summary.capacity.pdfLimit} /></p></div>
              <div><h3>Large-PDF admission threshold</h3><p><EvidenceMetric metric={summary.capacity.threshold} /></p>
                <p className="muted">A PDF above this ordinary threshold activates additional CPU-profile and host-resource admission checks.</p>
              </div>
            </div>
            <h3>Historical release-image optimization</h3>
            <div className="engineering-table-wrap">
              <table>
                <caption>Historical release-image optimization</caption>
                <thead><tr><th scope="col">Image</th><th scope="col">Recorded size</th></tr></thead>
                <tbody>
                  <tr><th scope="row">Original packaging</th><td><EvidenceMetric metric={summary.images.original} /></td></tr>
                  <tr><th scope="row">Optimized CPU image</th><td><EvidenceMetric metric={summary.images.optimized} /></td></tr>
                  <tr><th scope="row">Recorded A-to-C reduction</th><td><EvidenceMetric metric={summary.images.reduction} /></td></tr>
                </tbody>
              </table>
            </div>
            <p className="muted">The current CPU image was measured separately at <EvidenceMetric metric={summary.images.current} />. The earlier optimized image is from a separate historical qualification, not the current image.</p>
            <details>
              <summary>Recorded end-to-end performance</summary>
              <p>In the recorded population ({summary.levelC.populationLabel}), median end-to-end generation-path latency was <EvidenceMetric metric={summary.levelC.endToEndP50} />. The generation-only p50 was <EvidenceMetric metric={summary.levelC.generationP50} /> in that same recorded population.</p>
              <p className="muted">This is descriptive evidence from one recorded machine/model configuration, not a release latency target. The retrieval p50 above comes from a different population and measures a different part of the path.</p>
              <EvidenceLink evidenceId="performance.slice14-level-c" />
            </details>
            <p className="muted"><strong>How measured.</strong> Current runtime profiles and limits come from accepted product qualification/policy; historical image sizes and latency values retain their original populations.</p>
            <EvidenceLink evidenceId={summary.evidence.runtimeId} />
            <EvidenceLink evidenceId={summary.evidence.capacityId}>Inspect capacity evidence</EvidenceLink>
            <EvidenceLink evidenceId={summary.evidence.releaseId}>Inspect release evidence</EvidenceLink>
          </Card>

          <Card className="stack" id="not-shipped">
            <h2>Several capabilities were held back when the evidence did not justify shipping them.</h2>
            <div className="engineering-summary-story">
              <h3>Learned free-text router</h3>
              <p>
                A learned router was tested, but an unseen Spanish request that
                mixed a factual question with a conversation action entered the
                conversation-only lane. That lane does not retrieve evidence,
                so the router crossed the grounding boundary and was rejected.
              </p>
              <p><strong>Status:</strong> Rejected by the grounding safety rule. Explicit application-owned transformations were shipped instead; ordinary factual requests remain grounded.</p>
            </div>
            <div className="engineering-summary-story">
              <h3>Automatic query retry</h3>
              <p><strong>Status:</strong> Built and evaluated; evidence was insufficient, so product recovery remains disabled.</p>
              <p>{summary.decisions.recoveryEfficacy} · {summary.decisions.recoveryStatus}</p>
            </div>
            <div className="engineering-summary-story">
              <h3>Security campaign</h3>
              <p>
                The adversarial campaign completed, but a required security
                measurement could not be evaluated on its accepted test surface.
                The campaign therefore failed closed under its rules.
              </p>
              <p><strong>Status:</strong> Fail-closed because a required measurement could not be evaluated. This does not mean every attack succeeded, and it does not establish security completeness.</p>
            </div>
            <p className="engineering-takeaway">Predefined gates kept uncertain behavior out of the product instead of treating implementation completion as proof that a capability should ship.</p>
            <p className="muted"><strong>How measured.</strong> These decisions are summarized from the accepted conversation, recovery, and security records; no new campaign was run for this page.</p>
            <EvidenceLink evidenceId={summary.evidence.decisionsId} />
            <EvidenceLink evidenceId={summary.evidence.recoveryId}>Inspect recovery evidence</EvidenceLink>
            <EvidenceLink evidenceId={summary.evidence.securityId}>Inspect security evidence</EvidenceLink>
          </Card>

          <Card className="stack" id="verify-claims">
            <h2>The Summary is the explanation; Evidence is the audit trail.</h2>
            <p>
              Summary measurements are projected from versioned accepted
              evidence. The Evidence page retains the source links, populations,
              qualifications, and decision context behind those claims.
            </p>
            <p className="muted"><strong>How measured.</strong> The bundled manifest is validated before these semantic selections are rendered. Missing or incompatible evidence makes the Summary unavailable instead of substituting stale values.</p>
            <div className="row">
              <Link className="button" to="/engineering/evidence">Inspect evidence</Link>
              <Link className="button button-secondary" to="/engineering/architecture">See architecture</Link>
            </div>
          </Card>
        </div>
      );
  }

  return (
    <div className="stack engineering-page">
      <header className="stack engineering-page-header" style={{ gap: "0.5rem" }}>
        <h1>Engineering summary</h1>
        <p style={{ margin: 0 }}>What the evidence says about Seneca’s design, behavior, and trade-offs.</p>
        <EngineeringNav />
      </header>
      {content}
    </div>
  );
}
