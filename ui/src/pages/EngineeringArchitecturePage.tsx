import { Card } from "../components/Card";
import { EngineeringNav } from "../features/engineering/EngineeringNav";

function Diagram({ children }: { children: string }) {
  return (
    <pre className="engineering-diagram" tabIndex={0}>
      {children}
    </pre>
  );
}

export function EngineeringArchitecturePage() {
  return (
    <div className="stack engineering-page">
      <header className="stack" style={{ gap: "0.5rem" }}>
        <h1>Architecture</h1>
        <p className="muted" style={{ margin: 0 }}>
          Explanatory diagrams based on accepted architecture. Not live telemetry.
        </p>
        <EngineeringNav />
      </header>

      <Card className="stack">
        <h2>Product architecture</h2>
        <p className="muted" style={{ margin: 0 }}>
          Active grounded product path used by Seneca and the product API.
        </p>
        <Diagram>{`Seneca React UI
      ↓
FastAPI adapter
      ↓
offline_rag.app
      ↓
workspace / admission / query orchestration
      ↓
dense + lexical retrieval
      ↓
RRF
      ↓
reranker
      ↓
context assembly
      ↓
evidence sufficiency
      ↓
local generation client
      ↓
answer blocks / citations / provenance`}</Diagram>
      </Card>

      <Card className="stack">
        <h2>Snapshot / data architecture</h2>
        <p className="muted" style={{ margin: 0 }}>
          Workspace mutations after admission do not silently upgrade prior
          answers. Current / Historical provenance reflects snapshot binding.
        </p>
        <Diagram>{`source versions
      ↓
workspace revision
      ↓
immutable admitted snapshot
      ↓
query / conversational turn
      ↓
bound evidence + provenance

workspace may mutate afterward
but admitted turn remains snapshot-bound
→ Current / Historical`}</Diagram>
      </Card>

      <Card className="stack">
        <h2>Deployment architecture</h2>
        <p className="muted" style={{ margin: 0 }}>
          Generator weights remain outside the application image. Normal
          strict-offline operation does not require cloud inference; initial
          model provisioning may still require prior downloads.
        </p>
        <Diagram>{`Browser
   ↓
OfflineRAG application container
   ├── built Seneca frontend
   ├── FastAPI
   ├── app/product layer
   ├── Qdrant Local
   └── retrieval model runtime
         │
         ├── /data
         └── /models

OfflineRAG application
   ↓ approved local OpenAI-compatible endpoint

Host generation runtime
   └── Ollama default`}</Diagram>
      </Card>

      <Card className="stack">
        <h2>Deferred / not active</h2>
        <p className="muted" style={{ margin: 0 }}>
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
