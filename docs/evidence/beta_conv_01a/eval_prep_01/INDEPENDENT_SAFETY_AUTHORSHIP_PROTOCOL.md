# Independent Safety Challenge Authorship Protocol

**Status:** Prepared; zero new families authored.

An independent reviewer/authorship group that did not implement or prompt the
planner must author at least 40 new semantic safety families, at least 15 in
Spanish. A family is a distinct failure mechanism or safety boundary, not a
paraphrase or generated variation of another case. Keep language, family
identity, source/context setup, expected operation, permitted safe outcomes,
required evidence sources, severity, and rationale with each authored case.

Keep historical challenges separate from new authorship. Record author
provenance privately, then have a second independent reviewer inspect family
distinctness, language count, label validity, and coverage before acceptance.
Do not reveal or use model outputs to author, revise, or label these cases.

The 40 JSONL rows in `new_safety_family_slots.jsonl` are empty placeholders, not
safety examples and not evidence of authorship. Do not count paraphrases or
automatic variants toward the minimum.
