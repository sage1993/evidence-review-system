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

  function setProtectedMode(protectedMode) {
    document.querySelectorAll("[data-protected-only]").forEach((node) => {
      node.hidden = !protectedMode;
    });
    document.querySelectorAll("[data-archive-only]").forEach((node) => {
      node.hidden = protectedMode;
    });
  }

  function updateReviewerSession() {
    const node = document.querySelector("[data-reviewer-session]");
    if (!node) return;
    node.textContent = decisionContext.reviewer_id
      ? "검토자: " + decisionContext.reviewer_id
      : "보관 HTML에서는 저장 시 검토자 ID를 확인합니다.";
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

  function notesRequired(decision) {
    return Boolean(decision && decision !== "SATISFIED");
  }

  function syncNotesRequirement() {
    const selected = document.querySelector('input[name="decision"]:checked');
    const notes = document.getElementById("review-notes");
    if (!notes) return;
    const required = notesRequired(selected ? selected.value : "");
    notes.required = required;
    notes.setAttribute("aria-required", required ? "true" : "false");
    if (!required) {
      notes.removeAttribute("aria-invalid");
      const error = document.getElementById("notes-error");
      if (error) error.hidden = true;
    }
  }

  function validateNotes(decision, notesValue) {
    const notes = document.getElementById("review-notes");
    const error = document.getElementById("notes-error");
    const invalid = notesRequired(decision) && !String(notesValue || "").trim();
    if (notes) {
      if (invalid) notes.setAttribute("aria-invalid", "true");
      else notes.removeAttribute("aria-invalid");
    }
    if (error) error.hidden = !invalid;
    return !invalid;
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
    if (!validateNotes(request.decision, request.notes) || !validDecisionRequest(request)) return null;
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
      node.textContent = statusLabel(status);
    });
  }

  async function refreshDisplayStatus() {
    try {
      const response = await fetch("./decision/status");
      if (!response.ok) {
        setProtectedMode(false);
        return;
      }
      const payload = await response.json();
      applyDisplayStatus(payload.display_status);
      if (typeof payload.reviewer_id === "string" && payload.reviewer_id) {
        decisionContext.reviewer_id = payload.reviewer_id;
      }
      if (typeof payload.packet_hash === "string" && payload.packet_hash) {
        decisionContext.packet_hash = payload.packet_hash;
      }
      setProtectedMode(true);
      updateReviewerSession();
    } catch (_) {
      setProtectedMode(false);
      updateReviewerSession();
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

  function selectReviewItem(itemId) {
    document.querySelectorAll(".review-item, .detail-panel").forEach((node) => {
      const selected = node.dataset.itemId === itemId;
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
    let assetKey = "";
    if (typeof evidenceId === "undefined") {
      assetKey = itemId;
    } else {
      selectReviewItem(itemId);
      const citation = Array.from(document.querySelectorAll(".citation")).find((node) => {
        const panel = node.closest(".detail-panel");
        return panel && panel.dataset.itemId === itemId && node.dataset.evidenceId === evidenceId;
      });
      assetKey = citation ? citation.dataset.assetKey : "";
      document.querySelectorAll(".citation").forEach((node) => {
        node.classList.toggle("is-selected", node === citation);
      });
    }
    if (!assetKey) return;
    document.querySelectorAll(".evidence-page").forEach((page) => {
      page.classList.toggle("is-active", page.dataset.assetKey === assetKey);
    });
    document.querySelectorAll(".citation-overlay").forEach((overlay) => {
      overlay.classList.toggle(
        "is-focused",
        Boolean(evidenceId) && overlay.dataset.evidenceId === evidenceId
      );
    });
    const page = Array.from(document.querySelectorAll(".evidence-page")).find(
      (node) => node.dataset.assetKey === assetKey
    );
    if (page) page.focus({ preventScroll: true });
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
    const selected = form.querySelector('input[name="decision"]:checked');
    const notes = form.querySelector('[name="notes"]');
    const decision = selected ? selected.value : "";
    const notesValue = notes ? notes.value : "";
    syncNotesRequirement();
    if (!form.reportValidity() || !validateNotes(decision, notesValue)) return;
    const request = decisionRequest(form);
    if (!validDecisionRequest(request)) {
      formStatus("결정 저장에 필요한 정보를 확인하십시오.");
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
        formStatus("검토자 결정이 저장되었습니다.");
      } else {
        formStatus("결정 저장이 거부되었습니다. 입력과 현재 검토 자료를 확인하십시오.");
      }
    } catch (_) {
      formStatus("보관 HTML에서는 서버 저장을 사용할 수 없습니다. 결정 JSON을 다운로드하십시오.");
    }
  }

  function downloadDecisionEnvelope() {
    const form = document.querySelector("#decision-form form");
    if (!form) return;
    const selected = form.querySelector('input[name="decision"]:checked');
    const notes = form.querySelector('[name="notes"]');
    const decision = selected ? selected.value : "";
    const notesValue = notes ? notes.value : "";
    syncNotesRequirement();
    if (!form.reportValidity() || !validateNotes(decision, notesValue)) return;
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
    formStatus("결정 JSON을 다운로드했습니다.");
  }

  window.selectReviewItem = selectReviewItem;
  window.activateDetailTab = activateDetailTab;
  window.focusEvidence = focusEvidence;
  window.setEvidenceZoom = setEvidenceZoom;
  window.submitDecision = submitDecision;
  window.refreshDisplayStatus = refreshDisplayStatus;
  window.downloadDecisionEnvelope = downloadDecisionEnvelope;

  document.querySelectorAll(".review-item").forEach((item) => {
    item.addEventListener("click", () => selectReviewItem(item.dataset.itemId));
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
      if (panel) focusEvidence(panel.dataset.itemId, link.dataset.evidenceId);
    });
  });
  document.querySelectorAll("button[data-viewer-mode]").forEach((button) => {
    button.addEventListener("click", () => setEvidenceMode(button.dataset.viewerMode));
  });
  document.querySelectorAll('input[name="decision"]').forEach((input) => {
    input.addEventListener("change", syncNotesRequirement);
  });
  const notes = document.getElementById("review-notes");
  if (notes) notes.addEventListener("input", () => validateNotes(
    document.querySelector('input[name="decision"]:checked')?.value || "",
    notes.value
  ));
  const zoom = document.getElementById("evidence-zoom");
  if (zoom) zoom.addEventListener("input", () => setEvidenceZoom(zoom.value));
  const form = document.querySelector("#decision-form form");
  if (form) form.addEventListener("submit", submitDecision);
  const download = document.querySelector("[data-download-decision]");
  if (download) download.addEventListener("click", downloadDecisionEnvelope);
  const printButton = document.querySelector("[data-print]");
  if (printButton) printButton.addEventListener("click", () => window.print());
  window.addEventListener("beforeprint", revealPrintPanels);
  window.addEventListener("afterprint", restorePrintPanels);
  updateTabControls(selectedDetailPanel());
  syncNotesRequirement();
  setProtectedMode(false);
  updateReviewerSession();
  void refreshDisplayStatus();

  void reviewModel;
}());