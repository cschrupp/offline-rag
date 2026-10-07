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

export type RevealMap = Record<string, TurnRevealState>;

/**
 * Resolve an explicit map entry, or fall back to fully visible.
 * AskPanel uses a stricter answered-turn fail-closed default when Training Mode
 * is active and the entry is unanswered in the map yet.
 */
export function revealForEntry(
  map: RevealMap,
  entryId: string,
): TurnRevealState {
  return (
    map[entryId] ?? {
      answer: true,
      citations: true,
      evidence: true,
    }
  );
}

export function withRevealPatch(
  map: RevealMap,
  entryId: string,
  patch: Partial<TurnRevealState>,
): RevealMap {
  const current = revealForEntry(map, entryId);
  return {
    ...map,
    [entryId]: {
      answer: patch.answer ?? current.answer,
      citations: patch.citations ?? current.citations,
      evidence: patch.evidence ?? current.evidence,
    },
  };
}
