(() => {
  const BUNDLE_SCHEMA = "offline-rag-pages-review-bundle-v1";
  const RESULT_SCHEMA = "offline-rag-pages-review-result-v1";

  const state = {
    bundle: null,
    reviews: {}, // draft_case_id -> working review
    currentId: null,
    cases: [],
    detail: null,
  };

  const el = {
    runMeta: document.getElementById("run-meta"),
    caseList: document.getElementById("case-list"),
    casePanel: document.getElementById("case-panel"),
    bundleFile: document.getElementById("bundle-file"),
    btnDownload: document.getElementById("btn-download-result"),
    btnClear: document.getElementById("btn-clear-progress"),
    btnPrev: document.getElementById("btn-prev-case"),
    btnNext: document.getElementById("btn-next-case"),
    btnNextPending: document.getElementById("btn-next-pending"),
    btnNextHigh: document.getElementById("btn-next-high"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function canonicalizeQuery(text) {
    if (text == null) return null;
    const t = String(text).trim();
    return t || null;
  }

  function canonicalizeCategory(text) {
    if (text == null) return null;
    const t = String(text).trim();
    return t || null;
  }

  function canonicalizeTags(tags) {
    if (!Array.isArray(tags)) return [];
    const out = [];
    const seen = new Set();
    for (const item of tags) {
      const label = String(item ?? "").trim();
      if (!label || seen.has(label)) continue;
      seen.add(label);
      out.push(label);
    }
    return out;
  }

  function tagsEqual(a, b) {
    const left = canonicalizeTags(a);
    const right = canonicalizeTags(b);
    if (left.length !== right.length) return false;
    return left.every((v, i) => v === right[i]);
  }

  function storageKey(runId) {
    return `offline-rag-pages-review:${runId}`;
  }

  function emptyReview() {
    return {
      status: "pending",
      query_override: null,
      category_override: { is_overridden: false, value: null },
      tags_override: null,
      judgments: {},
      grade_basis_query: null,
    };
  }

  function ensureReview(draftId) {
    if (!state.reviews[draftId]) {
      state.reviews[draftId] = emptyReview();
    }
    return state.reviews[draftId];
  }

  function baseCase(draftId) {
    return state.bundle.cases.find((c) => c.draft_case_id === draftId);
  }

  function effectiveQuery(base, review) {
    if (review.query_override != null) return review.query_override;
    return canonicalizeQuery(base.proposed_query);
  }

  function effectiveCategory(base, review) {
    if (review.category_override && review.category_override.is_overridden) {
      return review.category_override.value;
    }
    return canonicalizeCategory(base.proposed_category);
  }

  function effectiveTags(base, review) {
    if (review.tags_override != null) return canonicalizeTags(review.tags_override);
    return canonicalizeTags(base.proposed_tags || []);
  }

  function proposalChanged(base, review) {
    const proposedQ =
      base.proposed_query != null ? canonicalizeQuery(base.proposed_query) : null;
    if (proposedQ !== effectiveQuery(base, review)) return true;
    if (canonicalizeCategory(base.proposed_category) !== effectiveCategory(base, review)) {
      return true;
    }
    return !tagsEqual(base.proposed_tags || [], effectiveTags(base, review));
  }

  function judgmentMap(review) {
    return { ...review.judgments };
  }

  function reviewComplete(base, review) {
    const ids = base.candidates.map((c) => c.chunk_id);
    const judged = judgmentMap(review);
    return ids.length > 0 && ids.every((id) => Object.prototype.hasOwnProperty.call(judged, id));
  }

  function positiveCount(review) {
    return Object.values(judgmentMap(review)).filter((g) => g >= 1).length;
  }

  function qualityEligible(base, review) {
    return reviewComplete(base, review) && positiveCount(review) >= 1;
  }

  function buildDetail(draftId) {
    const base = baseCase(draftId);
    if (!base) throw new Error(`unknown case: ${draftId}`);
    const review = ensureReview(draftId);
    const judged = judgmentMap(review);
    const eq = effectiveQuery(base, review);
    const changed = proposalChanged(base, review);
    const complete = reviewComplete(base, review);
    const pending = review.status === "pending";

    return {
      authoring_run_id: state.bundle.authoring_run_id,
      chunk_set_id: state.bundle.chunk_set_id,
      draft_case_id: draftId,
      status: review.status,
      proposed_query: base.proposed_query,
      effective_query: eq,
      proposed_category: base.proposed_category,
      effective_category: effectiveCategory(base, review),
      proposed_tags: canonicalizeTags(base.proposed_tags || []),
      effective_tags: effectiveTags(base, review),
      query_edited: changed && eq !== canonicalizeQuery(base.proposed_query),
      model_prelabels_for_proposed_query:
        eq !== canonicalizeQuery(base.proposed_query),
      judged_count: Object.keys(judged).length,
      candidate_count: base.candidates.length,
      human_positive_count: positiveCount(review),
      review_complete: complete,
      review_priority: base.review_priority || null,
      review_priority_reasons: base.review_priority_reasons || [],
      candidates: base.candidates.map((c) => ({
        ...c,
        human_relevance: Object.prototype.hasOwnProperty.call(judged, c.chunk_id)
          ? judged[c.chunk_id]
          : null,
      })),
      can_accept: pending && qualityEligible(base, review) && !changed,
      can_approve_edited: pending && qualityEligible(base, review) && changed,
      can_reject: pending,
      can_reopen: review.status !== "pending",
    };
  }

  function rebuildCaseList() {
    state.cases = state.bundle.cases.map((base, idx) => {
      const review = ensureReview(base.draft_case_id);
      const judged = judgmentMap(review);
      const detailLite = {
        status: review.status,
        judged_count: Object.keys(judged).length,
        candidate_count: base.candidates.length,
        effective_query: effectiveQuery(base, review),
        proposed_query: base.proposed_query,
        review_priority: base.review_priority || null,
        query_edited: proposalChanged(base, review),
      };
      return {
        ordinal: base.ordinal || idx + 1,
        draft_case_id: base.draft_case_id,
        ...detailLite,
      };
    });
  }

  function persist() {
    if (!state.bundle) return;
    const payload = {
      authoring_run_id: state.bundle.authoring_run_id,
      reviews: state.reviews,
      saved_at: new Date().toISOString(),
    };
    localStorage.setItem(storageKey(state.bundle.authoring_run_id), JSON.stringify(payload));
  }

  function restoreProgress(runId) {
    const raw = localStorage.getItem(storageKey(runId));
    if (!raw) return {};
    try {
      const parsed = JSON.parse(raw);
      if (parsed.authoring_run_id !== runId) return {};
      return parsed.reviews || {};
    } catch {
      return {};
    }
  }

  function setNavEnabled(on) {
    [
      el.btnDownload,
      el.btnClear,
      el.btnPrev,
      el.btnNext,
      el.btnNextPending,
      el.btnNextHigh,
    ].forEach((b) => {
      b.disabled = !on;
    });
  }

  function renderCaseList() {
    el.caseList.innerHTML = state.cases
      .map((c) => {
        const selected = c.draft_case_id === state.currentId ? "selected" : "";
        const priority = c.review_priority
          ? `<span class="badge ${escapeHtml(c.review_priority)}">${escapeHtml(c.review_priority)}</span>`
          : "";
        return `<button type="button" class="case-item ${selected}" data-id="${escapeHtml(c.draft_case_id)}">
          <div class="title">Case ${c.ordinal} of ${state.cases.length}</div>
          <div>${escapeHtml(c.effective_query || "(no query)")}</div>
          <div class="badges">
            <span class="badge ${escapeHtml(c.status)}">${escapeHtml(c.status)}</span>
            ${priority}
            <span class="badge">${c.judged_count}/${c.candidate_count}</span>
            ${c.query_edited ? '<span class="badge">Query edited</span>' : ""}
          </div>
        </button>`;
      })
      .join("");
    el.caseList.querySelectorAll(".case-item").forEach((btn) => {
      btn.addEventListener("click", () => loadCase(btn.dataset.id));
    });
  }

  function gradeLabel(value) {
    if (value === null || value === undefined) return "Unreviewed";
    return String(value);
  }

  function renderDetail() {
    const d = state.detail;
    if (!d) {
      el.casePanel.innerHTML = `<p class="muted">Select a case to begin review.</p>`;
      return;
    }

    const queryWarning = d.model_prelabels_for_proposed_query
      ? `<div class="warn">Model prelabels were generated for the original proposed query.</div>`
      : "";

    const candidates = d.candidates
      .map((c) => {
        const human = c.human_relevance;
        const p1 = c.model && c.model.pass_1
          ? `Pass 1: ${c.model.pass_1.grade} — ${escapeHtml(c.model.pass_1.rationale)}`
          : "Pass 1: —";
        const p2 = c.model && c.model.pass_2
          ? `Pass 2: ${c.model.pass_2.grade} — ${escapeHtml(c.model.pass_2.rationale)}`
          : "Pass 2: —";
        const agreement = c.agreement
          ? `Agreement: ${escapeHtml(c.agreement.agreement)} / ${escapeHtml(c.agreement.disagreement_severity)}`
          : "";
        const retrieval = (c.retrieval_provenance || [])
          .map(
            (h) =>
              `<li>${escapeHtml(h.retriever)} rank=${h.rank}${h.score == null ? "" : ` score=${h.score}`}</li>`
          )
          .join("");
        return `<article class="candidate" data-chunk="${escapeHtml(c.chunk_id)}">
          <h3>Candidate ${c.ordinal} / ${d.candidate_count}</h3>
          <div class="label">Document</div>
          <div>${escapeHtml(c.document_title || "(untitled)")}</div>
          <div class="label" style="margin-top:0.4rem">Section</div>
          <div>${escapeHtml(c.section || "(none)")}</div>
          <div class="label" style="margin-top:0.4rem">Source</div>
          <pre class="source-text">${escapeHtml(c.text)}</pre>
          <div class="label" style="margin-top:0.5rem">Your judgment (Human: ${escapeHtml(gradeLabel(human))})</div>
          <div class="grade-row">
            <button type="button" data-grade="0" class="${human === 0 ? "active" : ""}">0 Not relevant</button>
            <button type="button" data-grade="1" class="${human === 1 ? "active" : ""}">1 Supporting</button>
            <button type="button" data-grade="2" class="${human === 2 ? "active" : ""}">2 Direct answer</button>
          </div>
          ${c.is_source_seed ? `<span class="badge">Proposal source seed</span>` : ""}
          <div class="model-aid">
            <strong>Model prelabels — advisory only</strong><br/>
            ${p1}<br/>${p2}<br/>${agreement}
          </div>
          <details class="retrieval">
            <summary>Retrieval provenance</summary>
            <ul>${retrieval || "<li>(none)</li>"}</ul>
          </details>
        </article>`;
      })
      .join("");

    el.casePanel.innerHTML = `
      <div class="panel-card">
        <h2>Case review</h2>
        <p class="muted">Status: <strong>${escapeHtml(d.status)}</strong>
          · Reviewed ${d.judged_count} / ${d.candidate_count}
          · Positive ${d.human_positive_count}
          · Priority ${escapeHtml(d.review_priority || "n/a")}</p>
        ${queryWarning}
        <div class="label">Effective query — grade candidates against this</div>
        <textarea id="effective-query" rows="2">${escapeHtml(d.effective_query || "")}</textarea>
        <div class="label" style="margin-top:0.5rem">Original proposal</div>
        <p>${escapeHtml(d.proposed_query || "")}</p>
        <div class="label">Category</div>
        <input id="effective-category" type="text" value="${escapeHtml(d.effective_category || "")}" />
        <div class="label" style="margin-top:0.5rem">Tags (comma-separated)</div>
        <input id="effective-tags" type="text" value="${escapeHtml((d.effective_tags || []).join(", "))}" />
        <div class="actions">
          <button type="button" id="btn-save-meta">Save query / metadata</button>
          <button type="button" class="primary" id="btn-accept" ${d.can_accept ? "" : "disabled"}>Accept</button>
          <button type="button" class="primary" id="btn-edited" ${d.can_approve_edited ? "" : "disabled"}>Approve edited</button>
          <button type="button" class="danger" id="btn-reject" ${d.can_reject ? "" : "disabled"}>Reject</button>
          <button type="button" id="btn-reopen" ${d.can_reopen ? "" : "disabled"}>Reopen</button>
          <button type="button" id="btn-next-unreviewed">Next unreviewed</button>
        </div>
        <p id="case-error" class="error" hidden></p>
      </div>
      ${candidates}
    `;

    el.casePanel.querySelectorAll(".candidate").forEach((card) => {
      card.querySelectorAll("button[data-grade]").forEach((btn) => {
        btn.addEventListener("click", () => {
          try {
            setGrade(d.draft_case_id, card.dataset.chunk, Number(btn.dataset.grade));
          } catch (err) {
            showError(err.message);
          }
        });
      });
    });

    document.getElementById("btn-save-meta").onclick = saveMeta;
    document.getElementById("btn-accept").onclick = () => setStatus("accepted");
    document.getElementById("btn-edited").onclick = () => setStatus("edited");
    document.getElementById("btn-reject").onclick = () => setStatus("rejected");
    document.getElementById("btn-reopen").onclick = () => setStatus("pending");
    document.getElementById("btn-next-unreviewed").onclick = nextUnreviewed;
  }

  function showError(message) {
    const node = document.getElementById("case-error");
    if (!node) return;
    node.hidden = false;
    node.textContent = message;
  }

  function refreshAll() {
    rebuildCaseList();
    if (state.currentId) {
      state.detail = buildDetail(state.currentId);
    }
    el.runMeta.textContent = `${state.bundle.authoring_run_id} · ${state.bundle.corpus_name || "corpus"} · ${state.bundle.chunk_set_id || "no chunk set"} · ${state.bundle.cases.length} cases · local progress saved`;
    renderCaseList();
    renderDetail();
    persist();
  }

  function setGrade(draftId, chunkId, relevance) {
    const base = baseCase(draftId);
    const review = ensureReview(draftId);
    if (review.status === "accepted" || review.status === "edited" || review.status === "rejected") {
      throw new Error("reopen the case before changing grades");
    }
    if (![0, 1, 2].includes(relevance)) {
      throw new Error("human relevance must be strict integer 0, 1, or 2");
    }
    const ids = new Set(base.candidates.map((c) => c.chunk_id));
    if (!ids.has(chunkId)) throw new Error(`chunk_id not in candidate pool: ${chunkId}`);
    const eq = effectiveQuery(base, review);
    if (!eq) throw new Error("cannot grade candidates without an effective query");
    review.judgments[chunkId] = relevance;
    review.grade_basis_query = eq;
    refreshAll();
  }

  function saveMeta() {
    try {
      const base = baseCase(state.currentId);
      const review = ensureReview(state.currentId);
      if (review.status === "accepted" || review.status === "edited") {
        throw new Error("reopen the case before changing metadata");
      }
      const query = canonicalizeQuery(document.getElementById("effective-query").value);
      const categoryRaw = document.getElementById("effective-category").value;
      const category = canonicalizeCategory(categoryRaw);
      const tags = canonicalizeTags(
        document.getElementById("effective-tags").value.split(",")
      );

      const proposedQ = canonicalizeQuery(base.proposed_query);
      if (query === proposedQ) {
        review.query_override = null;
      } else {
        review.query_override = query;
      }

      const proposedCat = canonicalizeCategory(base.proposed_category);
      if (category === proposedCat) {
        review.category_override = { is_overridden: false, value: null };
      } else {
        review.category_override = { is_overridden: true, value: category };
      }

      const proposedTags = canonicalizeTags(base.proposed_tags || []);
      if (tagsEqual(tags, proposedTags)) {
        review.tags_override = null;
      } else {
        review.tags_override = tags;
      }

      // Semantic query change clears grades (9E).
      const basis = review.grade_basis_query;
      const newEq = effectiveQuery(base, review);
      if (basis != null && basis !== newEq) {
        review.judgments = {};
        review.grade_basis_query = null;
      }
      if (review.status === "rejected") {
        // allow meta edits only after reopen; already blocked above for accepted/edited
      }
      refreshAll();
    } catch (err) {
      showError(err.message);
    }
  }

  function setStatus(next) {
    try {
      const base = baseCase(state.currentId);
      const review = ensureReview(state.currentId);
      if (next === "accepted") {
        if (review.status !== "pending") throw new Error("only pending cases may be accepted");
        if (!qualityEligible(base, review)) {
          throw new Error("accept requires complete human map and at least one positive");
        }
        if (proposalChanged(base, review)) {
          throw new Error("proposal metadata changed; use approve edited instead");
        }
        review.status = "accepted";
      } else if (next === "edited") {
        if (review.status !== "pending") throw new Error("only pending cases may be approved as edited");
        if (!qualityEligible(base, review)) {
          throw new Error("approve-edited requires complete human map and at least one positive");
        }
        if (!proposalChanged(base, review)) {
          throw new Error("approve-edited requires a semantic change to query/category/tags");
        }
        review.status = "edited";
      } else if (next === "rejected") {
        if (review.status !== "pending") throw new Error("only pending cases may be rejected");
        review.status = "rejected";
      } else if (next === "pending") {
        if (review.status === "pending") throw new Error("case is already pending");
        review.status = "pending";
      } else {
        throw new Error(`unknown status: ${next}`);
      }
      refreshAll();
    } catch (err) {
      showError(err.message);
    }
  }

  function loadCase(id) {
    state.currentId = id;
    state.detail = buildDetail(id);
    renderCaseList();
    renderDetail();
  }

  function currentIndex() {
    return state.cases.findIndex((c) => c.draft_case_id === state.currentId);
  }

  function jump(predicate, startOffset = 1) {
    if (!state.cases.length) return;
    const start = Math.max(currentIndex(), 0);
    for (let i = 0; i < state.cases.length; i += 1) {
      const idx = (start + startOffset + i) % state.cases.length;
      if (predicate(state.cases[idx])) {
        loadCase(state.cases[idx].draft_case_id);
        return;
      }
    }
  }

  function nextUnreviewed() {
    if (!state.detail) return;
    const next = state.detail.candidates.find((c) => c.human_relevance == null);
    if (!next) return;
    const node = el.casePanel.querySelector(`[data-chunk="${CSS.escape(next.chunk_id)}"]`);
    if (node) node.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function validateBundle(bundle) {
    if (!bundle || typeof bundle !== "object") throw new Error("bundle must be a JSON object");
    if (bundle.schema_version !== BUNDLE_SCHEMA) {
      throw new Error(`unsupported schema_version (want ${BUNDLE_SCHEMA})`);
    }
    if (!bundle.authoring_run_id || !bundle.chunk_set_id) {
      throw new Error("bundle requires authoring_run_id and chunk_set_id");
    }
    if (!Array.isArray(bundle.cases) || !bundle.cases.length) {
      throw new Error("bundle.cases must be a non-empty array");
    }
    for (const c of bundle.cases) {
      if (!c.draft_case_id || !Array.isArray(c.candidates)) {
        throw new Error("each case requires draft_case_id and candidates[]");
      }
    }
  }

  function activateBundle(bundle) {
    validateBundle(bundle);
    state.bundle = bundle;
    state.reviews = restoreProgress(bundle.authoring_run_id);
    for (const c of bundle.cases) ensureReview(c.draft_case_id);
    setNavEnabled(true);
    refreshAll();
    const firstPending = state.cases.find((c) => c.status === "pending");
    const initial = firstPending || state.cases[0];
    if (initial) loadCase(initial.draft_case_id);
  }

  function downloadResult() {
    if (!state.bundle) return;
    const cases = state.bundle.cases.map((base) => {
      const review = ensureReview(base.draft_case_id);
      return {
        draft_case_id: base.draft_case_id,
        status: review.status,
        query_override: review.query_override,
        category_override: review.category_override,
        tags_override: review.tags_override,
        grade_basis_query: review.grade_basis_query,
        judgments: Object.entries(review.judgments).map(([chunk_id, relevance]) => ({
          chunk_id,
          relevance,
        })),
      };
    });
    const result = {
      schema_version: RESULT_SCHEMA,
      bundle_schema_version: BUNDLE_SCHEMA,
      authoring_run_id: state.bundle.authoring_run_id,
      chunk_set_id: state.bundle.chunk_set_id,
      corpus_name: state.bundle.corpus_name || null,
      exported_at: new Date().toISOString(),
      cases,
    };
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pages-review-result-${state.bundle.authoring_run_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  el.bundleFile.addEventListener("change", async () => {
    const file = el.bundleFile.files && el.bundleFile.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      activateBundle(JSON.parse(text));
    } catch (err) {
      el.runMeta.textContent = `Failed to load bundle: ${err.message}`;
      setNavEnabled(false);
    }
  });

  el.btnDownload.onclick = downloadResult;
  el.btnClear.onclick = () => {
    if (!state.bundle) return;
    if (!window.confirm("Clear local progress for this run id?")) return;
    localStorage.removeItem(storageKey(state.bundle.authoring_run_id));
    state.reviews = {};
    for (const c of state.bundle.cases) ensureReview(c.draft_case_id);
    refreshAll();
  };
  el.btnPrev.onclick = () => {
    const idx = currentIndex();
    if (idx > 0) loadCase(state.cases[idx - 1].draft_case_id);
  };
  el.btnNext.onclick = () => {
    const idx = currentIndex();
    if (idx >= 0 && idx < state.cases.length - 1) {
      loadCase(state.cases[idx + 1].draft_case_id);
    }
  };
  el.btnNextPending.onclick = () => jump((c) => c.status === "pending");
  el.btnNextHigh.onclick = () =>
    jump((c) => c.status === "pending" && c.review_priority === "high");

  // Optional convenience: private deploy may place bundle.json beside the site (not committed).
  fetch("./bundle.json")
    .then((res) => (res.ok ? res.json() : null))
    .then((bundle) => {
      if (bundle) activateBundle(bundle);
    })
    .catch(() => {
      /* file picker path remains available */
    });
})();
