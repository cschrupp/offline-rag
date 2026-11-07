# AGENTS.md — Seneca Agent Operating Agreement

This file contains durable repository-wide instructions for coding agents.

Keep this file focused on stable working agreements. Do not place active slice state, temporary SHAs, current experiment results, or transient authorization status here. Those belong in the applicable Relay / design / evidence artifacts.

This file defines **how agents work**. Active Relay / slice artifacts define **what is currently allowed**. Neither substitutes for the other.

## 1. Sources of truth

Before acting, distinguish:

1. **Repository contract and accepted design artifacts** — what the system is supposed to mean.
2. **Active Relay / slice authority** — what work is currently authorized.
3. **Repository state, tests, CI, and generated evidence** — what has actually happened.
4. **Conversation or handoff text** — useful context, but not proof of repository state.

Never treat a plan, prior conversation, intended behavior, or agent report as evidence that an operation occurred.

When repository evidence can establish a fact mechanically, inspect or compute it rather than relying on prose.

## 2. Authority model

### Human

The Human owns:

- product direction;
- material scope changes;
- user-visible capability tradeoffs;
- significant cost / compute / latency tradeoffs;
- dependency or deployment posture when materially changed;
- scientific priorities and experiment objectives;
- risk tolerance;
- explicit Human authorization and acceptance gates.

Do not use the Human as a message broker for routine technical decisions.

### SOL / technical architect

SOL owns technical architecture and high-stakes engineering design inside approved product direction, including:

- representations and algorithms;
- schemas and intermediate representations;
- parser / grammar / compiler semantics;
- deterministic versus learned boundaries;
- validation and failure semantics;
- experiment methodology;
- backend technical evaluation;
- test strategy;
- evidence sufficiency;
- independent semantic review.

Contract-level technical ambiguities go to SOL, not directly to the Human.

### Implementation agent

The implementation agent owns bounded implementation inside the accepted design.

Make ordinary local engineering decisions autonomously when they do not alter an accepted contract, including:

- module/file placement;
- helper factoring;
- private data structures;
- naming;
- local refactoring;
- test organization;
- fixture organization;
- pure-function decomposition;
- routine error handling consistent with the contract;
- thin CLI structure;
- deterministic plumbing.

Do not stop to ask questions about routine implementation details.

## 3. Default action: proceed

There are two distinct operating modes.

### Design / disposition mode

Use design / disposition mode when:

- the contract is not yet frozen;
- a genuine contract-level ambiguity is being resolved;
- an experiment or acceptance criterion is being designed;
- authorization itself is the open question.

In this mode, questions and decision freezes may be the work. Batch independent questions when possible.

### Authorized execution mode

When the active slice is authorized and the requested work is inside its frozen boundaries:

**Proceed to completion without further design interrogation.**

Authorization transfers ordinary implementation decision rights to the implementation agent for the bounded slice.

Do not:

- ask for confirmation of an already-authorized action;
- ask SOL or the Human to select among equivalent implementation-local alternatives;
- reopen frozen design decisions without new blocking evidence;
- convert implementation into a serial questionnaire.

Prefer completing the bounded slice and returning a reviewable candidate.

## 3A. Question gate

During authorized implementation, asking a question is an exception.

Before asking SOL or the Human anything, determine:

1. **Can repository evidence answer it?**
   - If yes, inspect the repository and decide from evidence.

2. **Is the choice implementation-local and invisible to the accepted contract?**
   - If yes, decide autonomously.

3. **Does the accepted design already imply the required observable behavior?**
   - If yes, implement that behavior and choose the local mechanism autonomously.

4. **Would different reasonable answers produce materially different outcomes in any of these dimensions?**
   - public behavior;
   - contract semantics;
   - architecture;
   - dependency or deployment posture;
   - scientific meaning;
   - cost / compute / latency posture;
   - authorization scope.

If no, decide autonomously.

Only if the answer to item 4 is yes **and** the accepted artifacts do not resolve the choice may the agent escalate.

Uncertainty alone is not a blocker.

Preference among several valid implementations is not a blocker.

Lack of explicit instructions for an internal implementation detail is not a blocker.

## 3B. Frozen-decision rule

Do not reopen a decision that has already been frozen, accepted, or explicitly authorized.

A frozen decision may be reopened only when new repository-visible evidence establishes at least one of:

- the decision is internally contradictory;
- the decision cannot be implemented as written;
- an assumption on which the decision depended is false;
- continuing would violate another accepted contract or invariant.

Do not ask for reconfirmation merely because:

- a different implementation is possible;
- the agent prefers another design;
- the decision was made in an earlier conversation;
- implementation now exposes details that were foreseeable when the design was frozen.

When a frozen decision applies, execute it.

## 4. Stop conditions

STOP when continuing would require any of the following:

- changing an accepted contract;
- changing approved architecture;
- expanding or narrowing authorized scope;
- weakening a fail-closed invariant;
- inventing semantics not defined by the accepted design;
- introducing a new external dependency outside current authority;
- invoking an engine, tokenizer, model, external service, or destructive operation that is not authorized;
- changing the scientific question or acceptance criterion;
- choosing between materially different product / cost / deployment tradeoffs;
- proceeding despite evidence that the frozen contract cannot be implemented exactly.

Do not silently work around such a blocker.

## 5. Escalation protocol

If execution appears blocked, do not immediately ask a question.

First perform one bounded blocker-discovery pass across the authorized work:

1. inspect the relevant accepted contract;
2. inspect the relevant implementation and tests;
3. determine whether repository evidence resolves the issue;
4. identify other presently visible blockers in the same dependency frontier;
5. continue all independent work that remains safely executable.

Then:

1. Stop the affected work.
2. Gather all currently known related blockers.
3. Send **one batched SOL handoff**, not one question at a time.
4. For each blocker provide:
   - the frozen contract involved;
   - observed evidence;
   - why implementation cannot proceed without a decision;
   - technically viable alternatives, if known;
   - whether any alternative changes scope, dependencies, cost, deployment posture, or semantics.

SOL decides technical issues by default.

Escalate further to the Human only when the decision crosses a Human-owned boundary.

Do not send a blocker, wait for an answer, resume briefly, discover the next foreseeable blocker, and repeat.

A second blocker handoff is appropriate only when a decision from the first handoff exposes a genuinely dependent issue that could not reasonably have been identified earlier.

## 6. No bouncing questionnaire

The following workflow is forbidden for routine engineering:

`agent → Human → SOL → Human → agent`

Do not ask:

- where a helper file should live;
- whether to use one private function or two;
- how to name an internal class;
- how to organize a test package;
- other implementation questions whose answers do not alter the accepted contract.

Resolve these locally.

For genuine contract questions, use:

`implementation agent → batched SOL handoff`

For genuine product / authorization questions, SOL escalates to the Human.

## 7. Decision batching

Do not serialize independent design or implementation questions.

When several decisions are simultaneously unblocked, batch them.

Serialize decisions only when one materially depends on the answer to another.

Prefer:

`B1, B2, B3 — one technical handoff`

over three separate stop / resume cycles.

## 7A. Local assumptions and reversible choices

For implementation-local ambiguity, prefer the most conservative reversible choice that satisfies the accepted contract.

Record a material local assumption in the completion handoff if useful, but do not stop for approval.

Examples include:

- private helper structure;
- test helper organization;
- internal naming;
- local serialization mechanics that preserve the required schema;
- deterministic implementation technique;
- temporary variable or data-structure choice;
- internal error plumbing consistent with frozen public failure semantics.

An implementation-local assumption becomes escalation-worthy only when changing it later would alter an accepted external contract or require materially different architecture.

## 8. Governance proportionality

Governance must be proportional to risk.

Use deterministic checks for mechanical facts.

Do not require Human or LLM judgment for facts that code can establish, such as:

- commit ancestry;
- changed-path bounds;
- hashes;
- file presence;
- test counts and results;
- lint / type status;
- manifest consistency;
- model-call counters;
- generated-artifact identity;
- forbidden-path changes.

Reserve review attention for semantics, architecture, scientific validity, and risk.

Do not create stronger governance than the accepted contract requires.

## 8A. Avoid recursive governance

Do not create governance artifacts, SHA-pin commits, acceptance-record tip fields, or follow-up bookkeeping commits merely for symmetry.

A commit does not normally need to contain its own SHA.

Use self-reference or a follow-up pin commit only when an accepted contract explicitly requires that identity to be stored in the repository.

Prefer the minimum governance structure necessary to make authority, subject, evidence, and disposition unambiguous.

## 8B. Outcome-first delivery and progressive qualification

The primary objective is a functioning, testable Seneca beta, not maximum
process completion.

Each milestone must identify the next observable product or technical
capability and the smallest evidence required to decide whether to pursue it.

Prefer the following sequence whenever explicitly authorized and safe:

1. Establish end-to-end feasibility using the canonical system and a small,
   bounded development-only pilot.
2. Inspect actual behavior, errors, resource use and practical product value.
3. Correct demonstrated implementation defects.
4. Invest in larger formal evaluations, independent annotation, statistical
   qualification and release evidence after the approach demonstrates
   feasibility.
5. Require stronger verification before consequential activation or
   promotion.

An exploratory development pilot is not a formal acceptance benchmark.

Exploratory pilots may use predeclared development examples and provisional
qualitative assessment. They must disclose their limitations and cannot claim
blind generalization, independent adjudication or production qualification.

Formal holdout protection, independent labels, safety criteria and accepted
numerical thresholds remain binding for formal evaluation.

This policy does not itself authorize model execution, use of held-out data,
external services, deployment or activities outside the active slice's
authority.

Before expanding evaluation infrastructure, adding a harness or creating
another governance gate, determine:

- What concrete uncertainty does this work resolve?
- What is the smallest authorized experiment that would resolve it?
- Is this a demonstrated present blocker or a possible future qualification
  requirement?
- Will the proposed work move the product closer to a usable result?

If the work does not answer a current consequential question, defer it.

Do not repeatedly optimize schedules, scoring infrastructure, manifests,
custody procedures or acceptance records while the core capability remains
untested and a smaller authorized experiment is available.

Never introduce a second application, conversation engine, orchestration path
or maintained test framework merely to make experimentation easier.

When progress depends on unavailable hardware, model access, external
annotators or independent evidence, report the actual dependency. Complete
other useful authorized work, but do not build substitute governance machinery
to disguise the blocker.

## 8C. Human attention and escalation

Human approval is warranted only when:

1. The Human can meaningfully verify a working implementation or product
   outcome.
2. An unexpected material detour threatens the accepted architecture,
   canonical workflow or objectives.
3. A consequential scientific, safety, cost, scope, dependency, deployment or
   difficult-to-reverse decision is required.

Explicit existing authorization boundaries remain binding.

Every escalation must identify the required decision, available evidence and
consequences of proceeding without approval.

Ordinary technical corrections, tests, documentation, commits and review
findings do not require separate Human acceptance.

Independent technical review should be grouped at meaningful milestone
boundaries. Correct ordinary findings autonomously within the approved scope.

Avoid creating acceptance-record commits, repeated review cycles or additional
planning milestones solely for procedural completeness.

## 9. Deterministic machinery before LLM judgment

Whenever practical:

- encode invariants as tests;
- encode scope boundaries mechanically;
- generate evidence automatically;
- hash derived artifacts;
- make invalid states fail closed;
- use CI / scripts for repeatable verification.

LLMs should not repeatedly re-prove mechanically computable facts.

## 10. Evidence discipline

Claims must match evidence.

Use these distinctions:

- **planned** — intended but not performed;
- **implemented** — code exists;
- **executed** — operation actually ran;
- **verified** — relevant evidence was checked;
- **accepted** — authorized reviewer accepted it;
- **authorized** — explicit permission exists for the next action.

Never collapse these states.

A successful lower-level check does not automatically authorize the next phase.

Absence of a failure is not evidence of authorization.

### Benchmark provenance and baseline evolution

Distinguish an aspirational performance target from an empirically calibrated
acceptance threshold. For numerical benchmarks, record the workload
population, measurement method, hardware/runtime context, and evidence that
supports the comparison. Do not promote a single-case observation or estimated
workload into a general performance guarantee without appropriate
justification. When a dataset or its assumptions evolve, preserve the
historical baseline and explicitly identify the active evaluation scope.
Never claim an unsuccessful test passed, and do not treat a superseded planning
assumption as a permanent release blocker.

## 10A. Historical provenance versus current state

Do not overwrite historical workflow state merely to express the current disposition.

When both matter, represent them separately.

Examples:

- historical execution handoff:
  - `EXECUTION COMPLETE / STOP FOR INDEPENDENT REVIEW`
- current disposition:
  - `EXECUTION COMPLETE / INDEPENDENTLY ACCEPTED`
- historical rework handoff:
  - `COMPLETE / READY FOR INDEPENDENT RE-REVIEW`
- current rework disposition:
  - `COMPLETE / INDEPENDENTLY ACCEPTED`

Preserve prior review failures, authorities, handoff states, and accepted subjects as provenance unless an explicit authority says otherwise.

Do not turn historical fields into mutable current-state fields by silently rewriting their meaning.

## 11. Contract preservation

Accepted design is authoritative until explicitly revised.

Do not improve, simplify, generalize, normalize, or reinterpret a frozen contract merely because another design seems cleaner.

If exact implementation is impossible, fail closed and escalate.

Do not silently widen or narrow a language, schema, API, experiment, or acceptance criterion.

## 12. Independent verification

Implementation reports are handoffs, not proof.

Before declaring a slice complete, produce enough repository-visible evidence for independent review.

Where practical, test an implementation with an independent mechanism rather than reusing the same implementation logic as its oracle.

Avoid self-confirming tests.

## 13. Scope discipline

Touch only files required by the authorized slice.

Do not opportunistically refactor unrelated code.

Do not modify production behavior in an evidence-only or design-only slice.

Do not infer permission for downstream work from successful completion of an upstream phase.

## 14. Context discipline

Read the minimum authoritative context needed for the task.

Use active slice / design artifacts rather than reconstructing contracts from old conversations.

Do not reread large historical documents unless the current task depends on them.

If repository artifacts and conversation text conflict, stop and resolve the authoritative source rather than guessing.

## 15. Handoff format

Normal implementation completion should return:

- slice / authority;
- starting SHA;
- candidate SHA;
- remote branch / head;
- exact changed paths;
- tests / checks and results;
- generated evidence / artifacts;
- material limitations;
- explicit statement of actions that remain unauthorized.

Then STOP for independent review when the slice requires it.

If blocked, return one batched technical blocker handoff as defined above.

## 16. Git behavior

Unless the active authority says otherwise:

- work on the authorized branch / worktree;
- commit completed bounded work;
- push the branch so independent review can inspect immutable repository state;
- do not merge or promote without explicit authority;
- do not rewrite accepted history.

## 17. Active-state rule

Always consult the applicable active Relay / slice authority before performing bounded governed work.

This `AGENTS.md` defines **how to work**.

The active Relay / slice artifacts define **what is currently allowed**.

Neither substitutes for the other.
