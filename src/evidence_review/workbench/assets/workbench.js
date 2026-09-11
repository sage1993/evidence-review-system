(() => {
  "use strict";

  function focusProvenance(button) {
    const targetId = button.getAttribute("aria-controls");
    const target = targetId ? document.getElementById(targetId) : null;
    if (!target) return;
    target.open = true;
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "nearest" });
  }

  function text(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function appendText(parent, tag, value, className) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text(value);
    parent.append(element);
    return element;
  }

  function readModel() {
    const model = document.getElementById("workbench-model");
    if (!model) return { evidence: [] };
    try {
      return JSON.parse(model.textContent || "{}");
    } catch (_) {
      return { evidence: [] };
    }
  }

  function requiresRecheck(result, model) {
    if (!Array.isArray(model.evidence)) return true;
    return !model.evidence.some((binding) => {
      const provenance = binding && binding.provenance;
      return provenance
        && provenance.evidence_snapshot_hash === result.evidence_snapshot_hash
        && provenance.evidence_db_sha256 === result.evidence_db_sha256;
    });
  }

  function appendNavigationProvenance(card, hit, result, index) {
    const citationId = text(hit.citation_id);
    const targetId = `navigation-provenance-${citationId}-${index}`;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "evidence-reference";
    button.dataset.navigationEvidenceId = text(hit.evidence_id);
    button.setAttribute("aria-controls", targetId);
    button.textContent = "정확한 출처 보기";
    button.addEventListener("click", () => focusProvenance(button));
    card.append(button);

    const details = document.createElement("details");
    details.id = targetId;
    details.tabIndex = -1;
    appendText(details, "summary", "정확한 출처");
    appendText(details, "p", `Citation ID: ${citationId}`);
    appendText(details, "p", `Evidence ID: ${text(hit.evidence_id)}`);
    appendText(details, "p", `Bounding box: ${Array.isArray(hit.bbox) ? hit.bbox.join(", ") : ""}`);
    appendText(details, "p", `Source hash: ${text(hit.source_hash)}`);
    appendText(details, "p", `Evidence snapshot: ${text(result.evidence_snapshot_hash)}`);
    appendText(details, "p", `Evidence DB: ${text(result.evidence_db_sha256)}`);
    card.append(details);
  }

  function renderNavigation(result, model) {
    const container = document.querySelector("[data-workbench-navigation-results]");
    if (!container) return;
    container.replaceChildren();
    appendText(container, "p", "탐색 결과 — 정식 근거로 확정되지 않음");
    const recheck = requiresRecheck(result, model);
    appendText(
      container,
      "p",
      recheck ? "재확인 필요" : "현재 선택 근거 스냅샷과 일치",
      recheck ? "recheck-marker" : "navigation-current"
    ).dataset.recheckRequired = String(recheck);

    const hits = Array.isArray(result.hits) ? result.hits : [];
    if (!hits.length) {
      appendText(container, "p", "일치하는 탐색 결과가 없습니다.", "empty-state");
      return;
    }
    hits.forEach((hit, index) => {
      const card = document.createElement("article");
      card.className = "navigation-hit";
      appendText(card, "h3", hit.title);
      appendText(card, "p", hit.text);
      appendText(
        card,
        "p",
        `${text(hit.document_id)} · ${text(hit.revision_id)} · p. ${text(hit.page_number)}`,
        "citation-location"
      );
      appendNavigationProvenance(card, hit, result, index);
      container.append(card);
    });
  }

  async function searchEvidence(form, model) {
    const status = document.querySelector("[data-workbench-navigation-status]");
    const value = new FormData(form).get("query");
    const query = typeof value === "string" ? value.trim() : "";
    if (!query || query.length > 240) return;
    if (status) status.textContent = "보존된 근거를 탐색하는 중입니다.";
    const searchUrl = new URL("./evidence/search", window.location.href);
    searchUrl.searchParams.set("query", query);
    searchUrl.searchParams.set("limit", "20");
    try {
      const response = await fetch(searchUrl, { headers: { Accept: "application/json" } });
      const result = await response.json();
      if (!response.ok || !Array.isArray(result.hits)) throw new Error("navigation failed");
      renderNavigation(result, model);
      if (status) status.textContent = `탐색 결과 ${result.hits.length}건`;
    } catch (_) {
      if (status) status.textContent = "보호된 Workbench 탐색을 다시 확인하십시오.";
    }
  }

  async function requestFormalization(button) {
    if (button.disabled) return;
    const expectedRevision = Number(button.dataset.formalizeExpectedRevision);
    if (!Number.isInteger(expectedRevision) || expectedRevision < 1) return;
    const status = document.querySelector("[data-formalize-status]");
    window.dispatchEvent(new CustomEvent("workbench:formalize", {
      detail: { expected_revision: expectedRevision }
    }));
    if (status) status.textContent = "현재 Matter revision으로 정식화 요청을 확인하는 중입니다.";
    try {
      const response = await fetch("./formalize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_revision: expectedRevision })
      });
      if (status) {
        status.textContent = response.ok
          ? "정식 검토 준비 요청이 접수되었습니다. 결과는 별도 정식 검토 흐름에서 확인합니다."
          : "정식화 요청이 거부되었습니다. Matter revision과 차단 항목을 다시 확인하십시오.";
      }
    } catch (_) {
      if (status) status.textContent = "보호된 Workbench 연결을 확인한 뒤 다시 요청하십시오.";
    }
  }

  const model = readModel();
  const navigationForm = document.querySelector("[data-workbench-navigation-form]");
  if (navigationForm) {
    navigationForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void searchEvidence(navigationForm, model);
    });
  }
  document.querySelectorAll("[data-evidence-reference]").forEach((button) => {
    button.addEventListener("click", () => focusProvenance(button));
  });
  const formalize = document.querySelector("[data-workbench-formalize]");
  if (formalize) formalize.addEventListener("click", () => requestFormalization(formalize));
}());
