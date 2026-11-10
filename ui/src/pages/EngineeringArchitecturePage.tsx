import { Card } from "../components/Card";
import { ArchitectureFlow } from "../features/engineering/ArchitectureFlow";
import { EngineeringNav } from "../features/engineering/EngineeringNav";

export function EngineeringArchitecturePage() {
  return (
    <div className="stack engineering-page">
      <header className="stack engineering-page-header" style={{ gap: "0.5rem" }}>
        <h1>Architecture</h1>
        <p style={{ margin: 0 }}>
          Five explanatory diagrams based on accepted architecture. They show
          system boundaries, not live telemetry.
        </p>
        <EngineeringNav />
      </header>

      <Card className="stack">
        <ArchitectureFlow
          title="Life of a question"
          data-testid="question-lifecycle-flow"
          layers={[
            { title: "Snapshot admission", detail: "active workspace · stored snapshot binding" },
            { title: "Dense + BM25 retrieval", detail: "current snapshot evidence" },
            { title: "RRF → BGE reranker", detail: "rank and select context" },
            { title: "Evidence sufficiency", detail: "answer or safely abstain" },
            { title: "Generation", detail: "local by default · optional approved REL-03 endpoint" },
            { title: "Citation membership", detail: "validate IDs against current EvidenceUnit[] and resolve provenance" },
          ]}
          notes={[
            "Membership validation does not prove semantic entailment or faithfulness.",
            "Explicit conversation actions branch from the selected transcript text to a text transform: no retrieval, query trace, or citations; the result is labeled not re-checked against sources.",
          ]}
        />
      </Card>

      <Card className="stack">
        <ArchitectureFlow
          title="Snapshot and provenance"
          data-testid="snapshot-architecture-flow"
          layers={[
            { title: "Source versions" },
            { title: "Workspace revision" },
            { title: "Admitted immutable snapshot" },
            { title: "Query or conversation action" },
            { title: "Evidence / transcript provenance" },
          ]}
          notes={[
            "Workspace changes later do not silently upgrade prior grounded answers.",
            "Conversation-action snapshot fields are workspace bookkeeping; they do not mean a transformation read or was grounded in that snapshot.",
          ]}
        />
      </Card>

      <Card className="stack">
        <ArchitectureFlow
          title="Runtime portability"
          data-testid="runtime-portability-flow"
          layers={[
            { title: "Installation capability", detail: "CPU-only release image or CUDA-capable local/developer installation" },
            { title: "AUTO resolver", detail: "the unchanged application policy selects a supported runtime for the installation" },
            { title: "Selected runtime profile", detail: "CPU release → cpu_onnx_fp32_v1 / CPUExecutionProvider OR CUDA-capable install → cuda_fp16_v1 / torch_st_v1" },
            { title: "Provisioned model assets", detail: "external to the application image and common to the supported runtime profiles" },
          ]}
          notes={[
            "REL-01 qualifies the CPU release artifact. CUDA runtime qualification does not mean a CUDA release image exists.",
            "CPU ONNX and CUDA FP16 are alternatives selected by the existing AUTO policy; presentation does not force CPU or add a resolver.",
          ]}
        />
      </Card>

      <Card className="stack">
        <ArchitectureFlow
          title="Deployment and trust boundary"
          data-testid="deployment-architecture-flow"
          layers={[
            { title: "Browser / packaged UI" },
            { title: "Seneca API and workspace data" },
            { title: "Local embeddings · retrieval · reranking" },
            { title: "Local evidence and citation authority" },
            { title: "Generation endpoint", detail: "strict-offline default · optional operator-selected REL-03" },
          ]}
          notes={[
            "Default operation is standalone and strict-offline. Initial provisioning may require separately managed downloads.",
            "REL-03's approved external inference seam covers grounded answer generation, explicit conversation transformations, and Gold authoring. Retrieval, embeddings, reranking, evidence selection, citation membership and provenance authority, and Gold truth remain local.",
          ]}
        />
      </Card>

      <Card className="stack">
        <ArchitectureFlow
          title="Evidence publication chain"
          data-testid="evidence-publication-flow"
          layers={[
            { title: "Frozen evidence" },
            { title: "Reviewed registry" },
            { title: "Deterministic exporter" },
            { title: "Static versioned manifest" },
            { title: "Read-only Engineering UI" },
          ]}
          notes={[
            "Source hashes and source-bound numeric facts are checked during export.",
            "Evidence flows one way from accepted artifacts to the portfolio; the UI does not execute experiments or modify product settings.",
          ]}
        />
      </Card>

      <Card className="stack engineering-deferred-card">
        <h2>Deferred / not active</h2>
        <p style={{ margin: 0 }}>
          These items are not part of the active Seneca execution path.
        </p>
        <ul>
          <li>Query/retrieval rewrite and retry recovery (Slice 12C) remains product-disabled after insufficient efficacy evidence.</li>
          <li>Operational crash/restart recovery is a separate accepted persistence capability that preserves the published snapshot and permits a subsequent operation.</li>
          <li>LangGraph adapter</li>
          <li>NeMo Guardrails</li>
          <li>Distributed Qdrant</li>
        </ul>
      </Card>

      <Card className="stack">
        <h2>Repository references</h2>
        <p className="muted" style={{ margin: 0 }}>
          Plain repository paths for provenance. Not bundled as in-app routes.
        </p>
        <ul className="engineering-source-list">
          <li><code>docs/slice16_design_authority.md</code></li>
          <li><code>docs/slice16_implementation_plan.md</code></li>
          <li><code>docs/slice16d_b3_conversational_workspace.md</code></li>
          <li><code>docs/slice16d_c_a4_closeout.md</code></li>
          <li><code>DEPLOYMENT.md</code></li>
          <li><code>ARCHITECTURE_DECISIONS.md</code></li>
        </ul>
      </Card>
    </div>
  );
}
