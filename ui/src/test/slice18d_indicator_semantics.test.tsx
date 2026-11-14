import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { EvidenceMetric } from "../features/engineering/EvidenceMetric";
import { formatIndicatorValue } from "../features/indicators/format";
import { renderWithProviders } from "./render";

describe("18D explicit indicator semantics", () => {
  it("formats proportions and ranking scores according to their definitions", () => {
    expect(formatIndicatorValue(0.909, "proportion", "fraction", 1)).toBe("90.9%");
    expect(formatIndicatorValue(0.091, "proportion", "fraction", 1)).toBe("9.1%");
    expect(formatIndicatorValue(0.8422, "ranking_score_0_1")).toBe("0.842");
    expect(formatIndicatorValue(0.9318, "ranking_score_0_1")).toBe("0.932");
    expect(formatIndicatorValue("UNLOADED", "status")).toBe("UNLOADED");
    expect(formatIndicatorValue(0, "count")).toBe("0");
    expect(formatIndicatorValue(1, "count")).toBe("1");
  });
  it("keeps percentage points distinct from relative percent changes", () => {
    expect(formatIndicatorValue(0.042, "percentage_point_delta", undefined, 1)).toBe("+4.2 pp");
    expect(formatIndicatorValue(0.053, "relative_percent_delta", undefined, 1)).toBe("+5.3%");
  });
  it("uses binary byte units and explicit throughput units", () => {
    expect(formatIndicatorValue(94371840, "byte_quantity")).toBe("90 MiB");
    expect(formatIndicatorValue(512, "byte_quantity")).toBe("512 B");
    expect(formatIndicatorValue(1024, "byte_quantity")).toBe("1 KiB");
    expect(formatIndicatorValue(1024 ** 3, "byte_quantity")).toBe("1 GiB");
    expect(formatIndicatorValue(18.43, "throughput", "embeddings/s", 1)).toBe("18.4 embeddings/s");
  });
  it("never converts absent measurements into zero or a loading state", () => {
    renderWithProviders(<><EvidenceMetric metric={{availability: "unavailable", value: null}} /><EvidenceMetric metric={{availability: "unevaluable", value: null}} /><EvidenceMetric metric={{availability: "not_applicable", value: null}} /></>);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Unevaluable")).toBeInTheDocument();
    expect(screen.getByText("Not applicable")).toBeInTheDocument();
    expect(screen.queryByText(/Loading/)).toBeNull();
  });
});
