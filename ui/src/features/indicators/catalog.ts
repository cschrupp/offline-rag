import catalog from "../../../../eval/presentation/indicator_catalog_v1.json";
import { formatIndicatorValue, type IndicatorDisplayKind } from "./format";

/** Presentation only: values remain owned by the named producer. */
export function formatDefinedIndicator(
  id: string,
  value: number | string,
): string {
  const definition = catalog.definitions.find(
    row => row.definition_id === id && row.definition_revision === 1,
  );
  if (!definition || (typeof value === "number" && !Number.isFinite(value))) {
    return "Unavailable";
  }
  return formatIndicatorValue(
    value,
    definition.display_kind as IndicatorDisplayKind,
    definition.canonical_unit,
    definition.precision,
  );
}
