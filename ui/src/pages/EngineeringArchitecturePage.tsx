import { Card } from "../components/Card";
import { ArchitectureFlow } from "../features/engineering/ArchitectureFlow";
import { EngineeringNav } from "../features/engineering/EngineeringNav";

export function EngineeringArchitecturePage() {
  return (
    <div className="stack engineering-page">
      <header className="stack engineering-page-header" style={{ gap: "0.5rem" }}>
        <h1>Architecture</h1>
        <p style={{ margin: 0 }}>
          Explanatory diagrams based on accepted architecture. Not live
          telemetry.
        </p>
        <EngineeringNav />
      </header>

      <Card className="stack">
        <ArchitectureFlow
          title="Product architecture"
          data-testid="product-architecture-flow"
          layers={[
            { title: "Seneca", detail: "React UI" },
            { title: "FastAPI", detail: "Product adapter" },
            {
              title: "Application / workspace core",
              detail: "admission · snapshots · query/conversation",
            },
            {
              title: "Retrieval & evidence",
              detail: "dense + lexical · RRF · rerank · context",
            },
            {
              title: "Grounded generation",
              detail:
                "sufficiency · local generator · answer blocks / citations / provenance",
            },
          ]}
          notes={[
            "Active grounded product path used by Seneca and the product API.",
          ]}
        />
      </Card>

      <Card className="stack">
        <ArchitectureFlow
          title="Snapshot / data architecture"
          data-testid="snapshot-architecture-flow"
          layers={[
            { title: "Source versions" },
            { title: "Workspace revision" },
            { title: "Admitted immutable snapshot" },
            { title: "Query / conversational turn" },
            { title: "Evidence + provenance" },
          ]}
          notes={[
            "Workspace changes later do not silently upgrade prior answers.",
            "Previous admitted turns remain snapshot-bound → Current / Historical provenance.",
          ]}
        />
      </Card>

      <Card className="stack">
        <ArchitectureFlow
          title="Deployment architecture"
          data-testid="deployment-architecture-flow"
          layers={[
            { title: "Browser" },
            {
              title: "OfflineRAG application container",
              detail:
                "Seneca frontend · FastAPI · app/product layer · Qdrant Local · retrieval models (/data, /models)",
            },
            {
              title: "Approved local OpenAI-compatible endpoint",
              detail: "Outside the application image",
            },
            {
              title: "Host generation runtime",
              detail: "Ollama default — generator weights not in the app container",
            },
          ]}
          notes={[
            "Normal strict-offline operation does not require cloud inference; initial model provisioning may still require prior downloads.",
          ]}
        />
      </Card>

      <Card className="stack engineering-deferred-card">
        <h2>Deferred / not active</h2>
        <p style={{ margin: 0 }}>
          These items are not part of the active Seneca execution path.
        </p>
        <ul>
          <li>product recovery</li>
          <li>LangGraph adapter</li>
          <li>NeMo Guardrails</li>
          <li>distributed Qdrant</li>
        </ul>
      </Card>

      <Card className="stack">
        <h2>Repository references</h2>
        <p className="muted" style={{ margin: 0 }}>
          Plain repository paths for provenance. Not bundled as in-app routes.
        </p>
        <ul className="engineering-source-list">
          <li>
            <code>docs/slice16_design_authority.md</code>
          </li>
          <li>
            <code>docs/slice16_implementation_plan.md</code>
          </li>
          <li>
            <code>docs/slice16d_b3_conversational_workspace.md</code>
          </li>
          <li>
            <code>docs/slice16d_c_a4_closeout.md</code>
          </li>
          <li>
            <code>DEPLOYMENT.md</code>
          </li>
          <li>
            <code>ARCHITECTURE_DECISIONS.md</code>
          </li>
        </ul>
      </Card>
    </div>
  );
}
