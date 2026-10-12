import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OperationProgress } from "../components/OperationProgress";
import {
  approximateEtaSeconds,
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

  it("omits ETA before threshold and when total unknown", () => {
    const now = Date.parse("2026-01-01T00:00:15Z");
    expect(
      approximateEtaSeconds({
        progress: {
          step: "embedding_chunks",
          current: 10,
          total: 100,
          unit: "chunks",
          started_at: "2026-01-01T00:00:10Z",
        },
        nowMs: now,
      }),
    ).toBeNull();
    expect(
      approximateEtaSeconds({
        progress: {
          step: "materializing_dense_index",
          current: 0,
          total: null,
          unit: "chunks",
          started_at: "2026-01-01T00:00:00Z",
        },
        nowMs: now,
      }),
    ).toBeNull();
    const eta = approximateEtaSeconds({
      progress: {
        step: "embedding_chunks",
        current: 20,
        total: 100,
        unit: "chunks",
        started_at: "2026-01-01T00:00:00Z",
      },
      nowMs: Date.parse("2026-01-01T00:00:20Z"),
    });
    expect(eta).toBeGreaterThan(0);
  });
});

describe("OperationProgress telemetry UI", () => {
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
      screen.getAllByText(/Building semantic search index/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText((_, el) =>
        Boolean(el?.textContent?.includes("384 / 1,216 chunks · 31%")),
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
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
