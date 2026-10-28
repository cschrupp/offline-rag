import { afterEach, describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OperationProgress } from "../components/OperationProgress";
import type {
  OperationWorklist,
  OperationWorklistDocument,
} from "../api/types";
import {
  appendUniqueFiles,
  validateUploadSelection,
} from "../features/workspaces/uploadStaging";
import {
  ACTIVE_OPERATIONS_KEY,
  rememberActiveOperation,
} from "../features/operations/activeOperations";
import {
  capabilities,
  errorResponse,
  installFetchMock,
  jsonResponse,
  operation,
  workspace,
} from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  localStorage.removeItem(ACTIVE_OPERATIONS_KEY);
});

const limits = {
  maxFilesPerUploadRequest: 1,
  maxBytesPerUploadedFile: 8 * 1024 * 1024,
  maxBytesPerPdfSource: 4 * 1024 * 1024,
  maxBytesPerUploadRequest: 10 * 1024 * 1024,
  maxActiveSources: 3,
  maxActiveSourceBytes: 12 * 1024 * 1024,
  largePdfRuntimeEligible: true,
};

function file(name: string, content: string, type: string, lastModified = 1): File {
  return new File([content], name, { type, lastModified });
}

describe("16K-E pre-submit staging", () => {
  it("appends in order and deduplicates an exact repeated selection", () => {
    const a = file("a.txt", "a", "text/plain");
    const b = file("b.txt", "bb", "text/plain");
    const repeatedA = file("a.txt", "a", "text/plain");

    expect(appendUniqueFiles([a], [b, repeatedA])).toEqual([a, b]);
  });

  it("attaches per-file errors and keeps request/workspace constraints aggregate", () => {
    const oversizedPdfWithTextMime = file(
      "manual.pdf",
      "x".repeat(5 * 1024 * 1024),
      "text/plain",
    );
    const textClaimingPdfMime = file(
      "notes.txt",
      "x".repeat(6 * 1024 * 1024),
      "application/pdf",
    );
    const result = validateUploadSelection({
      files: [oversizedPdfWithTextMime, textClaimingPdfMime],
      limits,
      existingSourceCount: 2,
      existingSourceBytes: 8 * 1024 * 1024,
    });

    expect(result.fileErrors[0]).toMatch(/manual\.pdf exceeds the 4\.0 MiB/);
    expect(result.fileErrors[1]).toBeNull();
    expect(result.aggregateErrors).toContain(
      "At most 1 file may be uploaded in one request.",
    );
    expect(result.aggregateErrors).toContain(
      "Selected files exceed the 10 MiB per-request upload limit.",
    );
    expect(result.aggregateErrors).toContain(
      "Selected files exceed the 12 MiB workspace source limit.",
    );
  });

  it("shows staged counts/bytes, removes one file, clears all, then submits only final membership", async () => {
    const user = userEvent.setup();
    let submittedNames: string[] = [];
    let submittedKey: string | null = null;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Upload Desk",
            revision: 1,
            source_count: 0,
            status: "empty",
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [] });
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "POST") {
        const form = call.body as FormData;
        submittedNames = (form.getAll("files") as File[]).map((item) => item.name);
        submittedKey = call.headers.get("Idempotency-Key");
        return jsonResponse(
          operation({ operation_id: "op_final", status: "pending" }),
          { status: 202 },
        );
      }
      if (call.url === "/v1/operations/op_final") {
        return jsonResponse(operation({ operation_id: "op_final", status: "running" }));
      }
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await user.click((await screen.findAllByRole("button", { name: "+ Add sources" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: /add sources/i });
    const input = within(dialog).getByLabelText(/source files/i);
    const a = file("a.txt", "alpha", "text/plain");
    const b = file("b.txt", "bravo", "text/plain");
    await user.upload(input, a);
    await user.upload(input, b);
    await user.upload(input, file("a.txt", "alpha", "text/plain"));

    expect(within(dialog).getByText(/Selected: 2 files · 10 B \(raw upload bytes\)/)).toBeInTheDocument();
    expect(within(dialog).getAllByRole("button", { name: /^Remove / })).toHaveLength(2);
    await user.click(within(dialog).getByRole("button", { name: "Remove a.txt" }));
    expect(within(dialog).getByText(/Selected: 1 file · 5 B \(raw upload bytes\)/)).toBeInTheDocument();
    expect(within(dialog).queryByText("a.txt · 5 B")).not.toBeInTheDocument();

    await user.upload(input, a);
    await user.click(within(dialog).getByRole("button", { name: "Clear all" }));
    expect(within(dialog).queryByLabelText("Selected upload files")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /^add sources$/i })).toBeDisabled();

    const finalFile = file("final.txt", "last", "text/plain");
    await user.upload(within(dialog).getByLabelText(/source files/i), finalFile);
    await user.click(within(dialog).getByRole("button", { name: /^add sources$/i }));
    await waitFor(() => expect(submittedNames).toEqual(["final.txt"]));
    expect(submittedKey).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /add sources/i })).toBeNull());
    mock.restore();
  });

  it("uses a new idempotency key after abandoning an ambiguous selection", async () => {
    const user = userEvent.setup();
    const postKeys: string[] = [];
    const postFiles: string[][] = [];
    let posts = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({ workspace_id: "ws_1", title: "Upload Desk", source_count: 0, status: "empty", current_snapshot_id: null }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [] });
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "POST") {
        posts += 1;
        postKeys.push(call.headers.get("Idempotency-Key") ?? "");
        postFiles.push(((call.body as FormData).getAll("files") as File[]).map((item) => item.name));
        if (posts === 1) throw new TypeError("Failed to fetch");
        return jsonResponse(operation({ operation_id: "op_new_intent", status: "pending" }), { status: 202 });
      }
      if (call.url === "/v1/operations/op_new_intent") {
        return jsonResponse(operation({ operation_id: "op_new_intent", status: "running" }));
      }
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await user.click((await screen.findAllByRole("button", { name: "+ Add sources" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: /add sources/i });
    const input = within(dialog).getByLabelText(/source files/i);
    await user.upload(input, file("first.txt", "first", "text/plain"));
    await user.click(within(dialog).getByRole("button", { name: /^add sources$/i }));
    await within(dialog).findByRole("button", { name: /retry safely/i });

    await user.upload(input, file("replacement.txt", "second", "text/plain"));
    expect(within(dialog).getByText(/Selected: 1 file · 6 B/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /^add sources$/i }));
    await waitFor(() => expect(posts).toBe(2));
    expect(postFiles).toEqual([["first.txt"], ["replacement.txt"]]);
    expect(postKeys[1]).not.toBe(postKeys[0]);
    mock.restore();
  });

  it("rebuilds worklist and metrics from the server after an active-operation reconnect", async () => {
    rememberActiveOperation({
      operation_id: "op_reconnect",
      workspace_id: "ws_1",
      kind: "source_add",
      label: "Add sources",
    });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/operations/op_reconnect") {
        return jsonResponse(
          operation({
            operation_id: "op_reconnect",
            status: "running",
            progress: {
              step: "embedding_chunks",
              current: 5,
              total: 10,
              unit: "chunks",
              started_at: new Date().toISOString(),
            },
            metrics: { embeddings_generated: 3, embeddings_reused: 2 },
            worklist: worklist(),
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(await screen.findByTestId("operation-tray")).toBeInTheDocument();
    expect(await screen.findByTestId("operation-active-documents")).toHaveTextContent(
      "Embedding passages from Fireground.pdf",
    );
    expect(screen.getByTestId("operation-embedding-counts")).toHaveTextContent(
      "Generated 3 · Reused 2 embeddings",
    );
    expect(screen.getByTestId("operation-worklist")).toBeInTheDocument();
    mock.restore();
  });
});

const document = (
  partial: Partial<OperationWorklistDocument> & Pick<OperationWorklistDocument, "document_id" | "display_name" | "phase">,
): OperationWorklistDocument => ({ ...partial });

const worklist = (partial: Partial<OperationWorklist> = {}): OperationWorklist => ({
  total_document_count: 2,
  pending_count: 1,
  completed_count: 0,
  remaining_count: 2,
  documents: [
    document({ document_id: "doc_a", display_name: "Fireground.pdf", phase: "indexing", child_chunk_count: 584 }),
    document({ document_id: "doc_b", display_name: "Manual.txt", phase: "pending" }),
  ],
  active_documents: [
    document({ document_id: "doc_a", display_name: "Fireground.pdf", phase: "indexing" }),
  ],
  ...partial,
});

describe("16K-E durable operation presentation", () => {
  it("shows active document, counts, progress, generated/reused work, throughput, and resolved device", () => {
    render(
      <OperationProgress
        phase="operation"
        operation={operation({
          operation_id: "op_compact",
          status: "running",
          created_at: new Date().toISOString(),
          progress: {
            step: "embedding_chunks",
            current: 20,
            total: 584,
            unit: "chunks",
            started_at: new Date().toISOString(),
          },
          metrics: {
            embeddings_generated: 16,
            embeddings_reused: 4,
            generated_chunks_per_sec: 8.4,
            dense_execution: { device: "cuda" },
            uploaded_raw_bytes: 4096,
          },
          worklist: worklist(),
        })}
      />,
    );

    expect(screen.getByTestId("operation-active-documents")).toHaveTextContent(
      "Embedding passages from Fireground.pdf",
    );
    expect(screen.getByTestId("operation-document-counts")).toHaveTextContent(
      "0 / 2 documents complete · 2 remaining",
    );
    expect(screen.getByTestId("operation-embedding-counts")).toHaveTextContent(
      "Generated 16 · Reused 4 embeddings",
    );
    expect(screen.getByTestId("operation-throughput")).toHaveTextContent(
      "8.4 new passages/s",
    );
    expect(screen.getByTestId("operation-execution-device")).toHaveTextContent("CUDA");
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.queryByText(/\bETA\b/i)).not.toBeInTheDocument();
  });

  it("represents multiple active documents without inventing a singular filename and expands the worklist", async () => {
    const user = userEvent.setup();
    render(
      <OperationProgress
        phase="operation"
        operation={operation({
          operation_id: "op_multi",
          status: "running",
          progress: { step: "embedding_chunks", current: 8, total: 20, unit: "chunks", started_at: new Date().toISOString() },
          worklist: worklist({
            total_document_count: 3,
            completed_count: 1,
            remaining_count: 2,
            documents: [
              document({ document_id: "doc_a", display_name: "Fireground.pdf", phase: "indexing" }),
              document({ document_id: "doc_b", display_name: "Manual.txt", phase: "pending" }),
              document({ document_id: "doc_c", display_name: "Indexed guide.pdf", phase: "indexed" }),
            ],
            active_documents: [
              document({ document_id: "doc_a", display_name: "Fireground.pdf", phase: "indexing" }),
              document({ document_id: "doc_b", display_name: "Manual.txt", phase: "indexing" }),
            ],
          }),
        })}
      />,
    );

    expect(screen.getByTestId("operation-active-documents")).toHaveTextContent(
      "Embedding passages across 2 documents",
    );
    expect(screen.getByTestId("operation-active-documents")).not.toHaveTextContent("Fireground.pdf");
    await user.click(screen.getByText("Worklist · 2 remaining of 3"));
    expect(screen.getByTestId("operation-worklist")).toHaveAttribute("open");
    const indexedRow = within(screen.getByTestId("operation-worklist")).getByText(
      "Indexed guide.pdf",
    ).closest("li");
    expect(indexedRow).toHaveTextContent("Indexed");
    const pendingRow = within(screen.getByTestId("operation-worklist")).getByText(
      "Manual.txt",
    ).closest("li");
    expect(pendingRow).toHaveTextContent("Pending");
    expect(screen.queryByText("Ready", { exact: true })).not.toBeInTheDocument();
  });

  it("puts detailed metrics and stage durations behind Details", async () => {
    const user = userEvent.setup();
    render(
      <OperationProgress
        phase="operation"
        operation={operation({
          operation_id: "op_details",
          status: "running",
          metrics: {
            requested_document_count: 2,
            pre_active_source_count: 3,
            post_active_source_count: 5,
            uploaded_raw_bytes: 4096,
            child_chunk_count: 12,
            model_input_tokens_per_sec: 25,
            dense_execution: {
              device: "cpu",
              dtype: "float32",
              batch_size: 8,
              attention_backend: "sdpa",
              embedding_dimension: 1024,
              profile_id: "cpu_onnx_fp32_v1",
            },
            stage_durations: { parsing_ms: 1000, dense_generation_ms: 2500 },
          },
        })}
      />,
    );

    expect(screen.getByTestId("operation-details")).toBeInTheDocument();
    expect(screen.getByTestId("operation-details")).not.toHaveAttribute("open");
    await user.click(screen.getByText("Details"));
    expect(screen.getByText("4.0 KiB")).toBeInTheDocument();
    expect(screen.getByText("cpu_onnx_fp32_v1")).toBeInTheDocument();
    expect(screen.getByText("2s")).toBeInTheDocument();
    expect(screen.queryByText(/\bETA\b/i)).not.toBeInTheDocument();
  });

  it("renders durable source-add success summary using backend values and terminal timestamps", () => {
    render(
      <OperationProgress
        phase="operation"
        operation={operation({
          operation_id: "op_success",
          kind: "source_add",
          status: "succeeded",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:01:42Z",
          metrics: {
            post_active_source_count: 13,
            child_chunk_count: 3227,
            embeddings_generated: 584,
            embeddings_reused: 2643,
          },
        })}
      />,
    );

    expect(screen.getByTestId("operation-success-summary")).toHaveTextContent(
      "13 sources ready · 3,227 searchable passages",
    );
    expect(screen.getByTestId("operation-success-summary")).toHaveTextContent(
      "Completed in 1m 42s",
    );
    expect(screen.getByTestId("operation-success-summary")).toHaveTextContent(
      "Generated 584 · Reused 2,643 embeddings",
    );
  });

  it("keeps historical null/absent telemetry valid and separates FAILED from INTERRUPTED", () => {
    const { rerender } = render(
      <OperationProgress
        phase="operation"
        operation={operation({
          operation_id: "op_legacy",
          status: "failed",
          error: { code: "ingest_failed", message: "Ingestion failed safely.", retryable: false },
        })}
      />,
    );
    expect(screen.getByText("Failed", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("Ingestion failed safely.")).toBeInTheDocument();
    expect(screen.queryByTestId("operation-details")).not.toBeInTheDocument();
    expect(screen.queryByTestId("operation-worklist")).not.toBeInTheDocument();

    rerender(
      <OperationProgress
        phase="operation"
        operation={operation({
          operation_id: "op_null_telemetry",
          status: "failed",
          metrics: null,
          worklist: null,
          error: { code: "ingest_failed", message: "Document ingestion failed.", retryable: false },
        })}
      />,
    );
    expect(screen.queryByTestId("operation-details")).not.toBeInTheDocument();
    expect(screen.queryByTestId("operation-worklist")).not.toBeInTheDocument();

    rerender(
      <OperationProgress
        phase="operation"
        operation={operation({ operation_id: "op_ocr", status: "failed", worklist: worklist({ documents: [document({ document_id: "doc_ocr", display_name: "Scanned handbook.pdf", phase: "requires_ocr" })], active_documents: [], total_document_count: 1, pending_count: 0, completed_count: 1, remaining_count: 0 }), error: { code: "ingest_failed", message: "Document ingestion failed.", retryable: false } })}
      />,
    );
    expect(screen.getByTestId("operation-ocr-failure")).toHaveTextContent(
      "OCR is required to read: Scanned handbook.pdf.",
    );

    rerender(
      <OperationProgress
        phase="operation"
        operation={operation({ operation_id: "op_interrupted", status: "interrupted", metrics: null, worklist: null })}
      />,
    );
    expect(screen.getByText("Interrupted", { exact: true })).toBeInTheDocument();
    expect(screen.getByText(/Processing was interrupted/)).toBeInTheDocument();
    expect(screen.queryByText("Failed", { exact: true })).not.toBeInTheDocument();
  });
});
