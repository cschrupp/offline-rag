/** Transient per-turn Training Mode reveal layers (UI only). */

export type TurnRevealState = {
  answer: boolean;
  citations: boolean;
  evidence: boolean;
};

export const HIDDEN_REVEAL: TurnRevealState = {
  answer: false,
  citations: false,
  evidence: false,
};

export const VISIBLE_REVEAL: TurnRevealState = {
  answer: true,
  citations: true,
  evidence: true,
};

export type RevealMap = Record<string, TurnRevealState>;

/**
 * Resolve reveal layers for a turn.
 * Training Mode answered turns must use HIDDEN_REVEAL when missing so the
 * first patch never inherits a fully-visible base (C-R1).
 */
export function revealForEntry(
  map: RevealMap,
  entryId: string,
  missingBase: TurnRevealState = HIDDEN_REVEAL,
): TurnRevealState {
  return map[entryId] ?? missingBase;
}

/**
 * Apply a partial reveal patch. Unspecified layers keep the current value,
 * and missing map entries use `missingBase` (default HIDDEN_REVEAL).
 */
export function withRevealPatch(
  map: RevealMap,
  entryId: string,
  patch: Partial<TurnRevealState>,
  missingBase: TurnRevealState = HIDDEN_REVEAL,
): RevealMap {
  const current = revealForEntry(map, entryId, missingBase);
  return {
    ...map,
    [entryId]: {
      answer: patch.answer ?? current.answer,
      citations: patch.citations ?? current.citations,
      evidence: patch.evidence ?? current.evidence,
    },
  };
}
