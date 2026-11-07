# Independent Annotation Assignment Protocol

**Status:** Prepared; no annotators assigned and no labels created.

Use the two local split-blind packets in the ignored evaluation-artifacts
directory. Assign each packet to a different annotator who did not implement
the planner or author its prompt. Do not share completed labels, discussion,
model output, or adjudication notes between annotators before both packets are
returned.

Each annotator must label all 300 cases independently under
`ANNOTATION_GUIDE.md`, including exact target identity, options, required
allowed-evidence source aliases, evidence requirement, clarification need,
expected reason, and permitted safe outcomes. Preserve the packet's case ID and
request hash. Reject malformed or incomplete rows; do not fill a label by
guessing.

The assignment owner should record opaque annotator identifiers and assignment
dates in a separate private provenance record. Keep both original label files
immutable. After both are complete, compute disagreements mechanically and
send only those cases plus the rubric to an adjudicator who has not seen model
output. Preserve the two originals, disagreement report, adjudication record,
and final label-file hash separately.

Do not merge packet outputs in place, expose split/stratum/family metadata to
annotators, use planner responses as labels, or describe Codex-generated
judgments as independent annotation.
