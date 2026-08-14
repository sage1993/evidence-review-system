(function () {
  "use strict";

  const modelNode = document.getElementById("review-model");
  const reviewModel = modelNode ? JSON.parse(modelNode.textContent || "{}") : {};
  const STATUS_LABELS = {
    ABSTAIN: "추가 자료 필요",
    READY_FOR_HUMAN_REVIEW: "검토 준비 완료",
    REVIEW_COMPLETED: "검토 완료",
    INDETERMINATE: "판단 보류",
    COMPLETE: "근거 연결 완료",
    MISSING_REQUIRED_INPUT: "필요한 자료가 부족합니다"
  };
  const VIEWER_LABELS = {
    original: "원문",
    evidence: "근거 강조",
    compare: "원문 + 강조"
  };
  const DECISION_LABELS = {
    SATISFIED: "검토 결과에 동의",
    NOT_SATISFIED: "검토 결과에 오류 있음",
    CONDITIONAL: "조건 충족 시 동의",
    ADDITIONAL_REVIEW_REQUIRED: "추가 자료 검토 필요"
  };
  const ALLOWED_DECISIONS = new Set([
    "SATISFIED",
    "NOT_SATISFIED",
    "CONDITIONAL",
    "ADDITIONAL_REVIEW_REQUIRED"
  ]);
  const decisionContext = {
    reviewer_id: "",
    packet_hash: reviewModel.decision && reviewModel.decision.packet_sha256
      ? reviewModel.decision.packet_sha256
      : ""
  };

  function statusLabel(status) {
    return STATUS_LABELS[status] || String(status || "상태 확인 필요").replace(/_/g, " ");
  }

  function formStatus(message) {
    const status = document.querySelector(".form-status");
    if (status) status.textContent = message;
  }

  function updateReviewerSession() {
    const node = document.querySelector("[data-reviewer-session]");
    if (!node) return;
    node.textContent = decisionContext.reviewer_id
      ? "검토자: " + decisionContext.reviewer_id + " · 보호 세션에서 확인됨"
      : "보관 HTML에서는 결정 JSON 다운로드 시 검토자 ID를 한 번 확인합니다.";
  }

  function validReviewerId(value) {
    return /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value);
  }

  function resolveReviewerId() {
    if (validReviewerId(decisionContext.reviewer_id)) return decisionContext.reviewer_id;
    const candidate = window.prompt("검토자 ID를 입력하십시오.", "") || "";
    if (!validReviewerId(candidate)) {
      formStatus("검토자 ID는 영문·숫자·점·밑줄·하이픈만 사용할 수 있습니다.");
      return "";
    }
    decisionContext.reviewer_id = candidate;
    updateReviewerSession();
    return candidate;
  }

  function decisionRequest(form) {
    const values = new FormData(form);
    const reviewerId = resolveReviewerId();
    return {
      reviewer_id: reviewerId,
      packet_hash: decisionContext.packet_hash || values.get("packet_sha256") || "",
      decision: values.get("decision") || "",
      notes: values.get("notes") || ""
    };
  }

  function notesRequired(decision) {
    return decision && decision !== "SATISFIED";
  }

  function validateNotesField(form) {
    const decision = form.querySelector('input[name="decision"]:checked');
    const notes = form.querySelector("#decision-notes");
    const error = document.getElementById("decision-notes-error");
    if (!notes) return true;
    const required = Boolean(decision && notesRequired(decision.value));
    notes.required = required;
    notes.setAttribute("aria-invalid", required && !notes.value.trim() ? "true" : "false");
    if (error) {
      error.textContent = required && !notes.value.trim() ? "이 결정을 선택하면 검토 의견을 입력해야 합니다." : "";
    }
    return !required || Boolean(notes.value.trim());
  }

  function validDecisionRequest(request) {
    return Boolean(
      validReviewerId(request.reviewer_id) &&
      /^[0-9a-f]{64}$/.test(request.packet_hash) &&
      ALLOWED_DECISIONS.has(request.decision) &&
      (!notesRequired(request.decision) || request.notes.trim())
    );
  }

  function decisionEnvelope(form) {
    const request = decisionRequest(form);
    if (!validDecisionRequest(request)) return null;
    return {
      reviewer_id: request.reviewer_id,
      reviewed_at: new Date().toISOString(),
      packet_hash: request.packet_hash,
      decision: request.decision,
      notes: request.notes
    };
  }

  function applyDisplayStatus(status) {
    if (!["READY_FOR_HUMAN_REVIEW", "REVIEW_COMPLETED"].includes(status)) return;
    reviewModel.display_status = status;
    document.querySelectorAll("[data-display-status]").forEach((node) => {
      node.textContent = node.dataset.displayStatusMode === "raw" ? status : statusLabel(status);
    });
  }

  function setProtectedMode(protectedMode) {
    document.querySelectorAll("[data-protected-only]").forEach((node) => {
      node.hidden = !protectedMode;
    });
    document.querySelectorAll("[data-archive-only]").forEach((node) => {
      node.hidden = protectedMode;
    });
  }

  function renderPersistedDecision(record) {
    const container = document.querySelector("[data-persisted-decision]");
    const editor = document.querySelector("[data-decision-editor]");
    if (!container || !editor) return;
    const valid = Boolean(
      record &&
      typeof record.reviewer_id === "string" &&
      typeof record.reviewed_at === "string" &&
      typeof record.decision === "string" &&
      typeof record.notes === "string" &&
      ALLOWED_DECISIONS.has(record.decision)
    );
    if (!valid) {
      container.hidden = true;
      editor.hidden = false;
      return;
    }
    const reviewer = container.querySelector("[data-persisted-reviewer]");
    const reviewedAt = container.querySelector("[data-persisted-reviewed-at]");
    const decision = container.querySelector("[data-persisted-decision-value]");
    const notes = container.querySelector("[data-persisted-notes]");
    if (reviewer) reviewer.textContent = record.reviewer_id;
    if (reviewedAt) reviewedAt.textContent = record.reviewed_at;
    if (decision) decision.textContent = DECISION_LABELS[record.decision] || record.decision;
    if (notes) notes.textContent = record.notes || "(의견 없음)";
    container.hidden = false;
    editor.hidden = true;
  }

  function beginAdditionalDecision() {
    const container = document.querySelector("[data-persisted-decision]");
    const editor = document.querySelector("[data-decision-editor]");
    const form = document.querySelector("#decision-form form");
    if (!editor || !form) return;
    if (container) container.hidden = true;
    editor.hidden = false;
    form.reset();
    const notes = form.querySelector("#decision-notes");
    if (notes) notes.required = false;
    const count = document.querySelector("[data-notes-count]");
    if (count) count.textContent = "0 / 1,000";
    formStatus("새 결정은 기존 기록을 수정하지 않고 별도 append-only 기록으로 추가됩니다.");
    const first = form.querySelector('input[name="decision"]');
    if (first) first.focus();
  }

  async function refreshDisplayStatus() {
    try {
      const response = await fetch("./decision/status");
      if (!response.ok) {
        setProtectedMode(false);
        renderPersistedDecision(null);
        return null;
      }
      const payload = await response.json();
      setProtectedMode(true);
      applyDisplayStatus(payload.display_status);
      if (typeof payload.reviewer_id === "string" && payload.reviewer_id) {
        decisionContext.reviewer_id = payload.reviewer_id;
      }
      if (typeof payload.packet_hash === "string" && payload.packet_hash) {
        decisionContext.packet_hash = payload.packet_hash;
      }
      renderPersistedDecision(payload.decision_record);
      updateReviewerSession();
      return payload;
    } catch (_) {
      setProtectedMode(false);
      renderPersistedDecision(null);
      updateReviewerSession();
      return null;
    }
  }

  function selectedDetailPanel() {
    return document.querySelector(".detail-panel.is-selected");
  }

  function selectedTabName() {
    const tab = document.querySelector('[data-detail-tab][aria-selected="true"]');
    return tab ? tab.dataset.detailTab : "evidence";
  }

  function updateTabControls(panel) {
    if (!panel) return;
    document.querySelectorAll("[data-detail-tab]").forEach((tab) => {
      const target = panel.querySelector('[data-tab-panel="' + tab.dataset.detailTab + '"]');
      if (target) tab.setAttribute("aria-controls", target.id);
    });
  }

  function selectReviewItem(itemId, evidenceId) {
    document.querySelectorAll(".review-item, .detail-panel").forEach((node) => {
      const selected = node.dataset.itemId === itemId && (!node.classList.contains("review-item") || !evidenceId || node.dataset.evidenceId === evidenceId);
      node.classList.toggle("is-selected", selected);
      if (node.classList.contains("review-item")) {
        node.setAttribute("aria-pressed", selected ? "true" : "false");
      }
    });
    const panel = selectedDetailPanel();
    updateTabControls(panel);
    activateDetailTab(selectedTabName());
  }

  function activateDetailTab(tabName) {
    document.querySelectorAll("[data-detail-tab]").forEach((tab) => {
      const selected = tab.dataset.detailTab === tabName;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.tabIndex = selected ? 0 : -1;
    });
    document.querySelectorAll(".detail-panel [data-tab-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.tabPanel !== tabName;
    });
    updateTabControls(selectedDetailPanel());
  }

  let printPanelStates = null;

  function revealPrintPanels() {
    if (printPanelStates !== null) return;
    const panels = Array.from(document.querySelectorAll(".detail-panel [data-tab-panel]"));
    printPanelStates = panels.map((panel) => ({ panel, hidden: panel.hidden }));
    panels.forEach((panel) => { panel.hidden = false; });
  }

  function restorePrintPanels() {
    if (printPanelStates === null) return;
    printPanelStates.forEach((state) => { state.panel.hidden = state.hidden; });
    printPanelStates = null;
  }

  function focusEvidence(itemId, evidenceId) {
    const citation = Array.from(document.querySelectorAll(".citation")).find((node) => {
      const panel = node.closest(".detail-panel");
      return panel && panel.dataset.itemId === itemId && node.dataset.evidenceId === evidenceId;
    });
    const assetKey = citation ? citation.dataset.assetKey : "";
    if (!assetKey) return false;

    setActivePage(assetKey);
    document.querySelectorAll(".citation-overlay").forEach((overlay) => {
      overlay.classList.toggle(
        "is-focused",
        overlay.dataset.evidenceId === evidenceId
      );
    });
    const page = Array.from(document.querySelectorAll(".evidence-page")).find(
      (node) => node.dataset.assetKey === assetKey
    );
    if (page) {
      page.scrollIntoView({ behavior: "smooth", block: "nearest" });
      page.focus({ preventScroll: true });
    }
    return true;
  }

  function focusItemEvidence(item) {
    return focusEvidence(item.dataset.itemId, item.dataset.evidenceId);
  }

  function resolveReviewItemEvidence(itemId, requestedEvidenceId) {
    const panel = Array.from(document.querySelectorAll(".detail-panel")).find(
      (node) => node.dataset.itemId === itemId
    );
    if (!panel) return "";

    if (requestedEvidenceId) {
      const requested = Array.from(panel.querySelectorAll(".citation")).find(
        (node) => node.dataset.evidenceId === requestedEvidenceId
      );
      if (requested) return requestedEvidenceId;
    }

    const first = panel.querySelector(".citation[data-evidence-id]");
    return first ? first.dataset.evidenceId : "";
  }

  function activateReviewItem(itemId, requestedEvidenceId) {
    selectReviewItem(itemId, requestedEvidenceId);
    const evidenceId = resolveReviewItemEvidence(itemId, requestedEvidenceId);
    if (!evidenceId) return false;
    return focusEvidence(itemId, evidenceId);
  }

  function setActivePage(assetKey) {
    const page = document.querySelector('.evidence-page[data-asset-key="' + assetKey + '"]');
    if (!page) return;
    document.querySelectorAll('.evidence-page').forEach((node) => {
      node.classList.toggle('is-active', node.dataset.assetKey === assetKey);
    });
    document.querySelectorAll('[data-page-select]').forEach((node) => {
      node.classList.toggle('is-active', node.dataset.pageSelect === assetKey);
    });
    const current = document.querySelector('[data-current-page]');
    const label = page.querySelector('figcaption');
    if (current && label) {
      const match = label.textContent.match(/(\d+)$/);
      if (match) current.textContent = match[1];
    }
  }

  function movePage(delta) {
    const pages = Array.from(document.querySelectorAll('.evidence-page'));
    const active = pages.findIndex((node) => node.classList.contains('is-active'));
    if (active < 0) return;
    const next = Math.max(0, Math.min(pages.length - 1, active + delta));
    setActivePage(pages[next].dataset.assetKey);
  }

  function enhanceReviewerSurface() {
    document.querySelectorAll("button[data-viewer-mode]").forEach((button) => {
      const label = VIEWER_LABELS[button.dataset.viewerMode];
      if (label) button.textContent = label;
    });
    const pageImages = new Map(
      Array.from(document.querySelectorAll("[data-page-image-source]")).map((image) => [
        image.dataset.pageImageSource,
        image.getAttribute("src") || ""
      ])
    );
    document.querySelectorAll("[data-page-image-for]").forEach((image) => {
      const source = pageImages.get(image.dataset.pageImageFor);
      if (source) image.setAttribute("src", source);
    });
  }

  function setEvidenceMode(mode) {
    if (!["original", "evidence", "compare"].includes(mode)) return;
    const shell = document.querySelector(".app-shell");
    if (shell) shell.dataset.viewerMode = mode;
    document.querySelectorAll("button[data-viewer-mode]").forEach((button) => {
      button.setAttribute("aria-pressed", button.dataset.viewerMode === mode ? "true" : "false");
    });
  }

  function setEvidenceZoom(scale) {
    document.querySelectorAll(".page-canvas").forEach((canvas) => {
      canvas.style.transform = "scale(" + scale + ")";
    });
  }

  async function submitDecision(event) {
    event.preventDefault();
    const form = event.currentTarget;
    validateNotesField(form);
    if (!form.reportValidity() || !validateNotesField(form)) return;
    const request = decisionRequest(form);
    if (!validDecisionRequest(request)) {
      formStatus("결정 저장에 필요한 검토자·패킷·결정·의견 정보를 확인하십시오.");
      return;
    }
    formStatus("검토자 결정을 저장하는 중입니다.");
    try {
      const response = await fetch("./decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request)
      });
      if (response.ok) {
        const payload = await response.json();
        applyDisplayStatus(payload.display_status);
        await refreshDisplayStatus();
        formStatus("검토자 결정이 별도 append-only 기록으로 저장되었습니다.");
      } else if (response.status === 409) {
        await refreshDisplayStatus();
        formStatus("이미 기록된 결정 상태를 다시 불러왔습니다. 새 기록이 필요하면 추가 결정 기록을 선택하십시오.");
      } else {
        formStatus("결정 저장이 거부되었습니다. 입력과 현재 패킷을 확인하십시오.");
      }
    } catch (_) {
      formStatus("보관 HTML에서는 서버 저장을 사용할 수 없습니다. 결정 JSON을 다운로드하십시오.");
    }
  }

  function downloadDecisionEnvelope() {
    const form = document.querySelector("#decision-form form");

    if (!form || !form.reportValidity()) return;
    const envelope = decisionEnvelope(form);
    if (!envelope) {
      formStatus("유효한 결정 JSON을 만들 수 없습니다. 입력을 확인하십시오.");
      return;
    }
    const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "human-decision-envelope.json";
    link.click();
    URL.revokeObjectURL(link.href);
    formStatus("유효한 5필드 결정 JSON을 다운로드했습니다. HTML 저장과는 별도입니다.");
  }

  window.selectReviewItem = selectReviewItem;
  window.activateDetailTab = activateDetailTab;
  window.focusEvidence = focusEvidence;
  window.focusItemEvidence = focusItemEvidence;
  window.resolveReviewItemEvidence = resolveReviewItemEvidence;
  window.activateReviewItem = activateReviewItem;
  window.setEvidenceZoom = setEvidenceZoom;
  window.submitDecision = submitDecision;
  window.refreshDisplayStatus = refreshDisplayStatus;
  window.renderPersistedDecision = renderPersistedDecision;
  window.beginAdditionalDecision = beginAdditionalDecision;
  window.downloadDecisionEnvelope = downloadDecisionEnvelope;

  document.querySelectorAll('.evidence-link, .citation[role="button"]').forEach((node) => {
    node.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      node.click();
    });
  });
  document.querySelectorAll('.citation[role="button"]').forEach((citation) => {
    citation.addEventListener("click", (event) => {
      if (event.target.closest(".evidence-link")) return;
      const panel = citation.closest(".detail-panel");
      if (panel) activateReviewItem(panel.dataset.itemId, citation.dataset.evidenceId);
    });
  });
  document.querySelectorAll(".review-item").forEach((item) => {
    item.addEventListener("click", () => {
      activateReviewItem(item.dataset.itemId);
    });
    item.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      activateReviewItem(item.dataset.itemId);
    });
  });
  document.querySelectorAll("[data-detail-tab]").forEach((tab) => {
    tab.addEventListener("click", () => activateDetailTab(tab.dataset.detailTab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const tabs = Array.from(document.querySelectorAll("[data-detail-tab]"));
      const current = tabs.indexOf(tab);
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
        (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next].focus();
      activateDetailTab(tabs[next].dataset.detailTab);
    });
  });
  document.querySelectorAll(".evidence-link").forEach((link) => {
    link.addEventListener("click", () => {
      const panel = link.closest(".detail-panel");
      if (panel) activateReviewItem(panel.dataset.itemId, link.dataset.evidenceId);
    });
  });
  document.querySelectorAll("button[data-viewer-mode]").forEach((button) => {
    button.addEventListener("click", () => setEvidenceMode(button.dataset.viewerMode));
  });
  document.querySelectorAll("[data-page-select]").forEach((button) => {
    button.addEventListener("click", () => setActivePage(button.dataset.pageSelect));
  });
  const previousPage = document.querySelector("[data-page-prev]");
  if (previousPage) previousPage.addEventListener("click", () => movePage(-1));
  const nextPage = document.querySelector("[data-page-next]");
  if (nextPage) nextPage.addEventListener("click", () => movePage(1));
  const fullscreen = document.querySelector("[data-fullscreen]");
  if (fullscreen) fullscreen.addEventListener("click", () => {
    const viewer = document.getElementById("evidence-viewer");
    if (viewer && viewer.requestFullscreen) void viewer.requestFullscreen();
  });
  let zoomScale = 1;
  const zoomValue = document.querySelector("[data-zoom-value]");
  function updateZoom(next) {
    zoomScale = Math.max(0.5, Math.min(2, next));
    setEvidenceZoom(zoomScale);
    if (zoomValue) zoomValue.textContent = Math.round(zoomScale * 100) + "%";
  }
  const zoomOut = document.querySelector("[data-zoom-out]");
  if (zoomOut) zoomOut.addEventListener("click", () => updateZoom(zoomScale - 0.1));
  const zoomIn = document.querySelector("[data-zoom-in]");
  if (zoomIn) zoomIn.addEventListener("click", () => updateZoom(zoomScale + 0.1));
  const additionalToggle = document.querySelector("[data-additional-toggle]");
  if (additionalToggle) additionalToggle.addEventListener("click", () => {
    const details = document.getElementById("additional-details");
    if (!details) return;
    details.hidden = !details.hidden;
    additionalToggle.setAttribute("aria-expanded", details.hidden ? "false" : "true");
  });
  const zoom = document.getElementById("evidence-zoom");
  if (zoom) zoom.addEventListener("input", () => setEvidenceZoom(zoom.value));
  const form = document.querySelector("#decision-form form");
  if (form) {
    form.querySelectorAll('input[name="decision"]').forEach((input) => {
      input.addEventListener("change", () => validateNotesField(form));
    });
    const notes = form.querySelector("#decision-notes");
    if (notes) notes.addEventListener("input", () => {
      validateNotesField(form);
      const count = document.querySelector("[data-notes-count]");
      if (count) count.textContent = notes.value.length.toLocaleString("en-US") + " / 1,000";
    });
    validateNotesField(form);
    form.addEventListener("submit", submitDecision);
  }
  const addDecision = document.querySelector("[data-add-decision]");
  if (addDecision) addDecision.addEventListener("click", beginAdditionalDecision);
  const download = document.querySelector("[data-download-decision]");
  if (download) download.addEventListener("click", downloadDecisionEnvelope);
  const printButton = document.querySelector("[data-print]");
  if (printButton) printButton.addEventListener("click", () => window.print());
  window.addEventListener("beforeprint", revealPrintPanels);
  window.addEventListener("afterprint", restorePrintPanels);
  enhanceReviewerSurface();
  updateTabControls(selectedDetailPanel());
  updateReviewerSession();
  void refreshDisplayStatus();

  void reviewModel;
}());