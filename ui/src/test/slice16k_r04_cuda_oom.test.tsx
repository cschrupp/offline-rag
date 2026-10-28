import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { OperationProgress } from "../components/OperationProgress";
import { operation } from "./mockApi";

afterEach(cleanup);

describe("16K-R04 CUDA memory recovery presentation", () => {
  it.each([16, 8])("shows a warning and effective batch after adapting to %i", (batchSize) => {
    render(
      <OperationProgress
        phase="operation"
        operation={operation({
          status: "succeeded",
          metrics: {
            dense_execution: {
              device: "cuda",
              configured_batch_size: 32,
              batch_size: batchSize,
            },
          },
        })}
      />,
    );

    expect(
      screen.getByText(`GPU memory constrained · batch reduced to ${batchSize}`),
    ).toBeInTheDocument();
    expect(screen.getByText(String(batchSize))).toBeInTheDocument();
    expect(screen.getByText("32")).toBeInTheDocument();
  });

  it("does not warn without adaptation or on CPU and renders historical execution facts", () => {
    const { rerender } = render(
      <OperationProgress
        phase="operation"
        operation={operation({
          status: "succeeded",
          metrics: {
            dense_execution: { device: "cuda", batch_size: 32 },
          },
        })}
      />,
    );
    expect(screen.queryByText(/GPU memory constrained/)).not.toBeInTheDocument();
    expect(screen.getByText("32")).toBeInTheDocument();

    rerender(
      <OperationProgress
        phase="operation"
        operation={operation({
          status: "succeeded",
          metrics: {
            dense_execution: {
              device: "cpu",
              configured_batch_size: 32,
              batch_size: 16,
            },
          },
        })}
      />,
    );
    expect(screen.queryByText(/GPU memory constrained/)).not.toBeInTheDocument();
    expect(screen.getByText("16")).toBeInTheDocument();
  });

  it("shows actionable copy and Compute settings only for the trusted OOM reason", () => {
    const { rerender } = render(
      <MemoryRouter>
        <OperationProgress
          phase="operation"
          operation={operation({
            status: "failed",
            error: {
              code: "ingest_failed",
              message: "Operation failed.",
              details: { stage: "dense", reason: "cuda_memory_exhausted" },
            },
          })}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("GPU memory was exhausted while building semantic search.")).toBeInTheDocument();
    expect(
      screen.getByText(/No new sources were published.*restart Seneca/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Compute settings" })).toHaveAttribute(
      "href",
      "/settings?section=compute",
    );

    rerender(
      <MemoryRouter>
        <OperationProgress
          phase="operation"
          operation={operation({
            status: "failed",
            error: {
              code: "ingest_failed",
              message: "Operation failed.",
              details: { stage: "dense", reason: "embedding_generation_failed" },
            },
          })}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("operation-cuda-memory-error")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open Compute settings" })).not.toBeInTheDocument();
  });
});
