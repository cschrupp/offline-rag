import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OperationProgress } from "../components/OperationProgress";
import {
  formatElapsed,
  progressPercent,
} from "../features/operations/progressTelemetry";
import { operation } from "./mockApi";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("progress telemetry helpers", () => {
  it("clamps percentage and formats elapsed", () => {
    expect(
      progressPercent({
        step: "embedding_chunks",
        current: 0,
        total: 100,
        unit: "chunks",
        started_at: "2026-01-01T00:00:00Z",
      }),
    ).toBe(0);
    expect(
      progressPercent({
        step: "embedding_chunks",
        current: 50,
        total: 100,
        unit: "chunks",
        started_at: "2026-01-01T00:00:00Z",
      }),
    ).toBe(50);
    expect(
      progressPercent({
        step: "embedding_chunks",
        current: 100,
        total: 100,
        unit: "chunks",
        started_at: "2026-01-01T00:00:00Z",
      }),
    ).toBe(100);
    expect(
      progressPercent({
        step: "embedding_chunks",
        current: 150,
        total: 100,
        unit: "chunks",
        started_at: "2026-01-01T00:00:00Z",
      }),
    ).toBe(100);
    expect(formatElapsed(14)).toBe("14s");
    expect(formatElapsed(74)).toBe("1m 14s");
  });
});

describe("OperationProgress telemetry UI", () => {
  it("uses Seneca in upload copy touched by 16I", () => {
    render(<OperationProgress phase="uploading" label="Add sources" />);
    expect(
      screen.getByText(/Sending files to Seneca/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/OfflineRAG/i)).not.toBeInTheDocument();
  });

  it("removes old coarse-only disclaimer and renders known denominator", () => {
    render(
      <OperationProgress
        phase="operation"
        label="Add sources"
        operation={operation({
          operation_id: "wop_pct",
          status: "running",
          progress_stage: "building_indexes",
          created_at: "2026-01-01T00:00:00Z",
          progress: {
            step: "embedding_chunks",
            current: 384,
            total: 1216,
            unit: "chunks",
            started_at: "2026-01-01T00:00:00Z",
          },
        })}
      />,
    );
    expect(
      screen.queryByText(/No percentage or ETA is shown/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Approx\.|remaining/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByText(/Building semantic search index/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText((_, el) =>
        Boolean(el?.textContent?.includes("384 / 1,216 chunks · 31%")),
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText(/Elapsed/i)).toBeInTheDocument();
  });

  it("renders indeterminate step without inventing a percentage", () => {
    render(
      <OperationProgress
        phase="operation"
        label="Add sources"
        operation={operation({
          operation_id: "wop_mat",
          status: "running",
          progress_stage: "building_indexes",
          created_at: "2026-01-01T00:00:00Z",
          progress: {
            step: "materializing_dense_index",
            current: 0,
            total: null,
            unit: "chunks",
            started_at: "2026-01-01T00:00:00Z",
          },
        })}
      />,
    );
    expect(
      screen.getAllByText(/Finalizing semantic search index/i).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("accepts progress null without regressing coarse stage labels", () => {
    render(
      <OperationProgress
        phase="operation"
        label="Add sources"
        operation={operation({
          operation_id: "wop_null",
          status: "running",
          progress_stage: "building_indexes",
          progress: null,
        })}
      />,
    );
    expect(
      screen.getAllByText(/Building search indexes/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByText(/No percentage or ETA is shown/i),
    ).not.toBeInTheDocument();
  });
});
