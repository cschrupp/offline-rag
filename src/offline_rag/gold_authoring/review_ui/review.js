(() => {
  const state = {
    cases: [],
    currentId: null,
    detail: null,
  };

  const el = {
    runMeta: document.getElementById("run-meta"),
    caseList: document.getElementById("case-list"),
    casePanel: document.getElementById("case-panel"),
  };

  async function api(path, options = {}) {
    const opts = { ...options };
    opts.headers = {
      ...(opts.headers || {}),
    };
    if (opts.body && !opts.headers["Content-Type"]) {
      opts.headers["Content-Type"] = "application/json";
    }
    const res = await fetch(path, opts);
    const data = await res.json();
    if (!data.ok) {
      const msg = (data.error && data.error.message) || "request failed";
      throw new Error(msg);
    }
    return data;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
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
        const p1 = c.model.pass_1
          ? `Pass 1: ${c.model.pass_1.grade} — ${escapeHtml(c.model.pass_1.rationale)}`
          : "Pass 1: —";
        const p2 = c.model.pass_2
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
        btn.addEventListener("click", async () => {
          try {
            await mutate(`/api/cases/${encodeURIComponent(d.draft_case_id)}/grade`, {
              chunk_id: card.dataset.chunk,
              relevance: Number(btn.dataset.grade),
            });
          } catch (err) {
            showError(err.message);
          }
        });
      });
    });

    document.getElementById("btn-save-meta").onclick = saveMeta;
    document.getElementById("btn-accept").onclick = () => action("accept");
    document.getElementById("btn-edited").onclick = () => action("approve-edited");
    document.getElementById("btn-reject").onclick = () => action("reject");
    document.getElementById("btn-reopen").onclick = () => action("reopen");
    document.getElementById("btn-next-unreviewed").onclick = nextUnreviewed;
  }

  function showError(message) {
    const node = document.getElementById("case-error");
    if (!node) return;
    node.hidden = false;
    node.textContent = message;
  }

  async function mutate(path, body) {
    const data = await api(path, { method: "POST", body: JSON.stringify(body) });
    state.detail = data.case;
    await refreshCaseList();
    renderDetail();
  }

  async function action(name) {
    try {
      await mutate(`/api/cases/${encodeURIComponent(state.currentId)}/${name}`, {});
    } catch (err) {
      showError(err.message);
    }
  }

  async function saveMeta() {
    const query = document.getElementById("effective-query").value;
    const category = document.getElementById("effective-category").value;
    const tagsRaw = document.getElementById("effective-tags").value;
    const tags = tagsRaw
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    try {
      await mutate(`/api/cases/${encodeURIComponent(state.currentId)}/query`, { query });
      await mutate(`/api/cases/${encodeURIComponent(state.currentId)}/category`, {
        category: category.trim() ? category : null,
        clear: !category.trim() && state.detail.proposed_category,
      });
      // If proposed category was null and input empty, clear means override-to-null only when intended.
      // Simpler path: empty input with proposed null => clear_override via tags-style.
      await mutate(`/api/cases/${encodeURIComponent(state.currentId)}/tags`, { tags });
    } catch (err) {
      showError(err.message);
    }
  }

  async function refreshCaseList() {
    const data = await api("/api/run");
    state.cases = data.cases;
    el.runMeta.textContent = `${data.run.authoring_run_id} · ${data.run.corpus_name || "corpus"} · ${data.run.chunk_set_id || "no chunk set"} · ${data.run.case_count} cases`;
    renderCaseList();
  }

  async function loadCase(id) {
    state.currentId = id;
    const data = await api(`/api/cases/${encodeURIComponent(id)}`);
    state.detail = data.case;
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

  document.getElementById("btn-prev-case").onclick = () => {
    const idx = currentIndex();
    if (idx > 0) loadCase(state.cases[idx - 1].draft_case_id);
  };
  document.getElementById("btn-next-case").onclick = () => {
    const idx = currentIndex();
    if (idx >= 0 && idx < state.cases.length - 1) {
      loadCase(state.cases[idx + 1].draft_case_id);
    }
  };
  document.getElementById("btn-next-pending").onclick = () =>
    jump((c) => c.status === "pending");
  document.getElementById("btn-next-high").onclick = () =>
    jump((c) => c.status === "pending" && c.review_priority === "high");

  (async function boot() {
    await refreshCaseList();
    const firstPending = state.cases.find((c) => c.status === "pending");
    const initial = firstPending || state.cases[0];
    if (initial) await loadCase(initial.draft_case_id);
  })().catch((err) => {
    el.runMeta.textContent = `Failed to load review: ${err.message}`;
  });
})();
