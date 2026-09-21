(function () {
  "use strict";

  const modelNode = document.getElementById("review-model");
  const reviewModel = modelNode ? JSON.parse(modelNode.textContent || "{}") : {};
  const STATUS_LABELS = {
    ABSTAIN: "현재 자료로 판정할 수 없음",
    READY_FOR_HUMAN_REVIEW: "검토 준비 완료",
    REVIEW_COMPLETED: "검토 기록 있음",
    INDETERMINATE: "판단 보류",
    COMPLETE: "근거 연결 완료",
    RESOLVED: "확인",
    PARTIALLY_RESOLVED: "일부 항목 확인",
    SOURCE_MISSING: "필요한 기준을 확인하지 못함",
    MISSING_REQUIRED_INPUT: "추가 자료 필요"
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

  function updateReviewerField() {
    const field = document.querySelector("#decision-reviewer-id");
    if (!field) return;
    if (decisionContext.reviewer_id) {
      field.value = decisionContext.reviewer_id;
      field.readOnly = true;
      field.setAttribute("aria-readonly", "true");
    } else {
      field.readOnly = false;
      field.removeAttribute("aria-readonly");
    }
  }

  function validReviewerId(value) {
    return /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value);
  }

  function resolveReviewerId(form) {
    const field = form ? form.querySelector("#decision-reviewer-id") : null;
    const candidate = field ? String(field.value || "").trim() : decisionContext.reviewer_id;
    if (!validReviewerId(candidate)) {
      if (field) {
        field.setCustomValidity("검토자 ID는 영문·숫자로 시작하며 영문·숫자·점·밑줄·하이픈만 사용할 수 있습니다.");
      }
      formStatus("검토자 ID는 영문·숫자·점·밑줄·하이픈만 사용할 수 있습니다.");
      return "";
    }
    if (field) field.setCustomValidity("");
    decisionContext.reviewer_id = candidate;
    updateReviewerField();
    updateReviewerSession();
    return candidate;
  }

  function decisionRequest(form) {
    const values = new FormData(form);
    const reviewerId = resolveReviewerId(form);
    return {
      reviewer_id: reviewerId,
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
      ALLOWED_DECISIONS.has(request.decision) &&
      (!notesRequired(request.decision) || request.notes.trim())
    );
  }

  function decisionEnvelope(form) {
    const request = decisionRequest(form);
    if (!validDecisionRequest(request)) return null;
    const packetHash = decisionContext.packet_hash || "";
    if (!/^[0-9a-f]{64}$/.test(packetHash)) return null;
    return {
      reviewer_id: request.reviewer_id,
      reviewed_at: new Date().toISOString(),
      packet_hash: packetHash,
      decision: request.decision,
      notes: request.notes
    };
  }

  function applyDisplayStatus(status) {
    if (!["READY_FOR_HUMAN_REVIEW", "REVIEW_COMPLETED"].includes(status)) return;
    reviewModel.display_status = status;
    document.querySelectorAll("[data-display-status]:not([data-machine-status])").forEach((node) => {
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
      editor.hidden = true;
      return;
    }
    const reviewer = container.querySelector("[data-persisted-reviewer]");
    const reviewedAt = container.querySelector("[data-persisted-reviewed-at]");
    const decision = container.querySelector("[data-persisted-decision-value]");
    const notes = container.querySelector("[data-persisted-notes]");
    if (reviewer) reviewer.textContent = record.reviewer_id;
    if (reviewedAt) {
      const date = new Date(record.reviewed_at);
      reviewedAt.textContent = Number.isNaN(date.getTime()) ? record.reviewed_at
        : new Intl.DateTimeFormat('ko-KR', {dateStyle: 'medium', timeStyle: 'short'}).format(date);
      reviewedAt.title = record.reviewed_at;
    }
    if (decision) decision.textContent = DECISION_LABELS[record.decision] || record.decision;
    if (notes) notes.textContent = record.notes || "(의견 없음)";
    container.hidden = false;
    editor.hidden = true;
    document.querySelector('[data-add-decision]')?.setAttribute('aria-expanded', 'false');
  }

  function beginAdditionalDecision() {
    const editor = document.querySelector("[data-decision-editor]");
    const form = document.querySelector("#decision-form form");
    if (!editor || !form) return;
    editor.hidden = false;
    document.querySelector('[data-add-decision]')?.setAttribute('aria-expanded', 'true');
    form.reset();
    const notes = form.querySelector("#decision-notes");
    if (notes) notes.required = false;
    updateReviewerField();
    const count = document.querySelector("[data-notes-count]");
    if (count) count.textContent = "0 / 1,000";
    formStatus("새 결정은 기존 기록을 수정하지 않고 별도 기록으로 추가됩니다.");
    const first = form.querySelector('input[name="decision"]');
    if (first) first.focus();
  }

  function cancelAdditionalDecision() {
    const editor = document.querySelector('[data-decision-editor]');
    const trigger = document.querySelector('[data-add-decision]');
    if (editor) editor.hidden = true;
    formStatus('');
    trigger?.setAttribute('aria-expanded', 'false');
    trigger?.focus();
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
      updateReviewerField();
      renderPersistedDecision(payload.decision_record);
      if (payload.decision_binding_status === "STALE") {
        formStatus("기존 결정은 이전 packet에 결속되어 있습니다. 현재 자료를 다시 검토하세요. (STALE)");
      }
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
  let printDetailStates = [];

  function revealPrintPanels() {
    if (printPanelStates !== null) return;
    const panels = Array.from(document.querySelectorAll(".detail-panel [data-tab-panel]"));
    printPanelStates = panels.map((panel) => ({ panel, hidden: panel.hidden }));
    panels.forEach((panel) => { panel.hidden = false; });
    printDetailStates = Array.from(document.querySelectorAll('#review-details, .decision-record-details'))
      .map(node => ({node, open: node.open}));
    printDetailStates.forEach(({node}) => { node.open = true; });
  }

  function restorePrintPanels() {
    if (printPanelStates === null) return;
    printPanelStates.forEach((state) => { state.panel.hidden = state.hidden; });
    printDetailStates.forEach(({node, open}) => { node.open = open; });
    printDetailStates = [];
    printPanelStates = null;
  }

  function isProtectedPresentation() {
    return Boolean(document.querySelector('[data-protected-presentation="true"]'));
  }

  function isProtectedFilePresentation() {
    return isProtectedPresentation() && window.location.protocol === "file:";
  }

  function applyFileProtocolGuidance() {
    const guidance = document.querySelector("[data-protected-file-guidance]");
    if (!guidance) return;
    const fileOpened = isProtectedFilePresentation();
    guidance.hidden = !fileOpened;
    if (fileOpened) {
      formStatus("보호된 검토기는 파일로 열 수 없습니다. 안내된 로컬 서버 명령을 실행하십시오.");
    }
  }

  function ensurePageImageLoaded(page) {
    if (!isProtectedPresentation() || isProtectedFilePresentation() || !page) return;
    const image = page.querySelector("img[data-page-image-source]");
    if (!image || image.getAttribute("src")) return;
    const source = image.dataset.pageSrc || "";
    if (source) image.setAttribute("src", source);
  }

  function prefetchAdjacentPages(page) {
    if (!isProtectedPresentation() || !page) return;
    const sourceId = page.dataset.sourceId || "";
    const pages = Array.from(document.querySelectorAll('.evidence-page[data-source-id="' + sourceId + '"]'));
    const activeIndex = pages.indexOf(page);
    if (activeIndex < 0) return;
    pages.forEach((candidate, index) => {
      if (Math.abs(index - activeIndex) <= 1) ensurePageImageLoaded(candidate);
    });
  }

  function activeSourceId() {
    const active = document.querySelector(".evidence-page.is-active");
    if (active && active.dataset.sourceId) return active.dataset.sourceId;
    const selector = document.querySelector("[data-source-select]");
    if (selector && selector.value) return selector.value;
    const first = document.querySelector(".evidence-page[data-source-id]");
    return first ? first.dataset.sourceId : "";
  }

  function setActiveSource(sourceId, requestedAssetKey) {
    if (!sourceId) return;
    const selector = document.querySelector("[data-source-select]");
    if (selector) selector.value = sourceId;
    document.querySelectorAll(".evidence-page[data-source-id]").forEach((page) => {
      const sameSource = page.dataset.sourceId === sourceId;
      page.hidden = !sameSource;
      if (!sameSource) page.classList.remove("is-active");
    });
    document.querySelectorAll("[data-page-select][data-source-id]").forEach((thumb) => {
      const sameSource = thumb.dataset.sourceId === sourceId;
      thumb.hidden = !sameSource;
      if (!sameSource) thumb.classList.remove("is-active");
    });
    const requested = requestedAssetKey
      ? document.querySelector('.evidence-page[data-asset-key="' + requestedAssetKey + '"][data-source-id="' + sourceId + '"]')
      : null;
    const target = requested || document.querySelector('.evidence-page[data-source-id="' + sourceId + '"]');
    if (target) setActivePage(target.dataset.assetKey);
  }

  function setActivePage(assetKey) {
    const page = document.querySelector('.evidence-page[data-asset-key="' + assetKey + '"]');
    if (!page) return;
    if (page.dataset.sourceId && page.dataset.sourceId !== activeSourceId()) {
      setActiveSource(page.dataset.sourceId, assetKey);
      return;
    }
    document.querySelectorAll('.evidence-page').forEach((node) => {
      node.classList.toggle('is-active', node.dataset.assetKey === assetKey);
    });
    document.querySelectorAll('[data-page-select]').forEach((node) => {
      node.classList.toggle('is-active', node.dataset.pageSelect === assetKey);
    });
    const position = document.querySelector('[data-current-source-position]');
    const count = document.querySelector('[data-current-source-count]');
    const original = document.querySelector('[data-current-original-page]');
    if (position) position.textContent = page.dataset.sourcePosition || "1";
    if (count) count.textContent = page.dataset.sourceCount || "1";
    if (original) original.textContent = page.dataset.originalPage || "";
    ensurePageImageLoaded(page);
    prefetchAdjacentPages(page);
  }

  function movePage(delta) {
    const sourceId = activeSourceId();
    const pages = Array.from(document.querySelectorAll('.evidence-page[data-source-id="' + sourceId + '"]'));
    const active = pages.findIndex((node) => node.classList.contains('is-active'));
    if (active < 0 || pages.length === 0) return;
    const next = Math.max(0, Math.min(pages.length - 1, active + delta));
    setActivePage(pages[next].dataset.assetKey);
  }

  function focusEvidence(itemId, evidenceId) {
    const citation = Array.from(document.querySelectorAll(".citation")).find((node) => {
      const panel = node.closest(".detail-panel");
      return panel && panel.dataset.itemId === itemId && node.dataset.evidenceId === evidenceId;
    });
    const assetKey = citation ? citation.dataset.assetKey : "";
    if (!assetKey) return false;
    const page = document.querySelector('.evidence-page[data-asset-key="' + assetKey + '"]');
    const sourceId = citation && citation.dataset.sourceId
      ? citation.dataset.sourceId
      : page && page.dataset.sourceId
        ? page.dataset.sourceId
        : "";
    if (sourceId) setActiveSource(sourceId, assetKey);
    else setActivePage(assetKey);
    document.querySelectorAll(".citation-overlay").forEach((overlay) => {
      overlay.classList.toggle(
        "is-focused",
        overlay.dataset.evidenceId === evidenceId
      );
    });
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

  function enhanceReviewerSurface() {
    document.querySelectorAll("button[data-viewer-mode]").forEach((button) => {
      const label = VIEWER_LABELS[button.dataset.viewerMode];
      if (label) button.textContent = label;
    });
    if (isProtectedPresentation()) return;
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
    const request = decisionRequest(form);
    if (!form.reportValidity() || !validateNotesField(form)) return;
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
        formStatus("검토자 결정이 새 기록으로 저장되었습니다.");
      } else if (response.status === 409) {
        await refreshDisplayStatus();
        formStatus("이미 기록된 결정 상태를 다시 불러왔습니다. 새 기록이 필요하면 새 결정 기록을 선택하십시오.");
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
  window.setActiveSource = setActiveSource;
  window.setActivePage = setActivePage;
  window.setEvidenceZoom = setEvidenceZoom;
  window.submitDecision = submitDecision;
  window.refreshDisplayStatus = refreshDisplayStatus;
  window.renderPersistedDecision = renderPersistedDecision;
  window.beginAdditionalDecision = beginAdditionalDecision;
  window.ensurePageImageLoaded = ensurePageImageLoaded;
  window.prefetchAdjacentPages = prefetchAdjacentPages;
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
  const sourceSelect = document.querySelector("[data-source-select]");
  if (sourceSelect) sourceSelect.addEventListener("change", () => setActiveSource(sourceSelect.value));
  document.querySelectorAll("[data-page-select]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.sourceId) setActiveSource(button.dataset.sourceId, button.dataset.pageSelect);
      else setActivePage(button.dataset.pageSelect);
    });
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
  document.querySelector('[data-cancel-decision]')?.addEventListener('click', cancelAdditionalDecision);
  const download = document.querySelector("[data-download-decision]");
  if (download) download.addEventListener("click", downloadDecisionEnvelope);
  const printButton = document.querySelector("[data-print]");
  if (printButton) printButton.addEventListener("click", () => window.print());
  window.addEventListener("beforeprint", revealPrintPanels);
  window.addEventListener("afterprint", restorePrintPanels);
  enhanceReviewerSurface();
  applyFileProtocolGuidance();
  updateTabControls(selectedDetailPanel());
  updateReviewerSession();
  updateReviewerField();
  const initial = document.querySelector(".evidence-page.is-active");
  if (initial && initial.dataset.sourceId) setActiveSource(initial.dataset.sourceId, initial.dataset.assetKey);
  void refreshDisplayStatus();

  void reviewModel;
}());

(()=>{const root=document.getElementById('case-visual-review');if(!root||root.dataset.bound==='1')return;root.dataset.bound='1';const pages=[...root.querySelectorAll('[data-case-page]')],cards=[...root.querySelectorAll('[data-case-finding]')],refs=[...root.querySelectorAll('[data-case-reference]')],overlays=[...root.querySelectorAll('[data-case-overlay]')],filterButtons=[...root.querySelectorAll('[data-case-filter]')];let pageIndex=0,activeCardIndex=cards.length?0:-1,filter='all',resultPage=0;const PAGE_SIZE=Math.max(1,cards.length),states=new WeakMap(),pageNo=root.querySelector('[data-case-page-number]'),zoomLabel=root.querySelector('[data-case-zoom]'),resultPageNo=root.querySelector('[data-finding-page-number]'),resultPageTotal=root.querySelector('[data-finding-page-total]');let tileFrame=0;function state(stage){let s=states.get(stage);if(!s){s={scale:1,x:0,y:0,drag:false,px:0,py:0};states.set(stage,s)}return s}function pageDimensions(page){return [Number(page?.dataset.pageWidth||0),Number(page?.dataset.pageHeight||0)]}function apply(stage){const s=state(stage),t=stage.querySelector('[data-case-transform]');if(t)t.style.transform=`translate(${s.x}px,${s.y}px) scale(${s.scale})`;if(zoomLabel&&pages[pageIndex]?.contains(stage))zoomLabel.textContent=`${Math.round(s.scale*100)}%`;scheduleVisibleTiles(pages[pageIndex]);syncViews(stage,false)}function pageFit(stage){if(!stage)return null;const page=pages.find(page=>page.contains(stage)),[pw,ph]=pageDimensions(page),rect=stage.getBoundingClientRect(),screen=Math.min(rect.width/pw,rect.height/ph);if(!(pw>0&&ph>0&&rect.width>0&&rect.height>0&&screen>0))return null;return{pw,ph,rect,screen,baseX:(rect.width-pw*screen)/2,baseY:(rect.height-ph*screen)/2}}function setPageFit(stage,targetFit){const fit=pageFit(stage);if(!fit||!(targetFit>0))return;const scale=targetFit/fit.screen,x=(fit.rect.width-fit.pw*targetFit)/2-fit.baseX*scale,y=(fit.rect.height-fit.ph*targetFit)/2-fit.baseY*scale;states.set(stage,{scale,x,y,drag:false,px:0,py:0});apply(stage)}function reset(stage){fitScreen(stage)}function fitScreen(stage){const fit=pageFit(stage);if(fit)setPageFit(stage,fit.screen)}function fitWidth(stage){const fit=pageFit(stage);if(fit)setPageFit(stage,fit.rect.width/fit.pw)}function originalSize(stage){setPageFit(stage,1)}function ensurePageRaster(page){if(!page)return;const full=page.querySelector('[data-case-page-image]');if(full&&!full.getAttribute('href'))full.setAttribute('href',full.dataset.casePageSrc||'');scheduleVisibleTiles(page)}function scheduleVisibleTiles(page){if(!page||tileFrame)return;tileFrame=requestAnimationFrame(()=>{tileFrame=0;ensureVisibleTiles(page)})}function ensureVisibleTiles(page){const stage=page?.querySelector('[data-case-stage]');if(!stage)return;const tiles=[...page.querySelectorAll('[data-case-tile]')];if(!tiles.length)return;const [pw,ph]=pageDimensions(page),rect=stage.getBoundingClientRect();if(!(pw>0&&ph>0&&rect.width>0&&rect.height>0))return;const fit=Math.min(rect.width/pw,rect.height/ph),ox=(rect.width-pw*fit)/2,oy=(rect.height-ph*fit)/2,s=state(stage),margin=Math.max(160,Math.min(rect.width,rect.height)*.25);tiles.forEach(tile=>{if(tile.getAttribute('href'))return;const x=Number(tile.dataset.tileX||0),y=Number(tile.dataset.tileY||0),w=Number(tile.dataset.tileWidth||0),h=Number(tile.dataset.tileHeight||0),left=s.x+(ox+x*fit)*s.scale,top=s.y+(oy+y*fit)*s.scale,right=left+w*fit*s.scale,bottom=top+h*fit*s.scale;if(right>=-margin&&bottom>=-margin&&left<=rect.width+margin&&top<=rect.height+margin)tile.setAttribute('href',tile.dataset.caseTileSrc||'')})}function showPage(key){const idx=pages.findIndex(p=>p.dataset.casePage===key);if(idx<0)return;pageIndex=idx;pages.forEach((p,i)=>{p.hidden=i!==idx;p.classList.toggle('is-active',i===idx)});if(pageNo)pageNo.textContent=String(idx+1);const jump=root.querySelector('[data-case-page-jump]');if(jump)jump.value=String(idx+1);ensurePageRaster(pages[idx]);const stage=pages[idx].querySelector('[data-case-stage]');if(stage)apply(stage)}const pageJump=root.querySelector('[data-case-page-jump]');function jumpToPage(){if(!pageJump||!pageJump.reportValidity())return;const n=Number(pageJump.value);if(Number.isInteger(n)&&n>=1&&n<=pages.length)showPage(pages[n-1].dataset.casePage)}root.querySelector('[data-case-page-go]')?.addEventListener('click',jumpToPage);pageJump?.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();jumpToPage()}});function candidateIds(card){return new Set((card?.dataset.caseCandidateIds||'').split('|').filter(Boolean))}function focusSubjectFinding(card){if(!card)return;showPage(card.dataset.casePageKey||'');requestAnimationFrame(()=>{const page=pages[pageIndex],stage=page?.querySelector('[data-case-stage]');if(!page||!stage)return;const bbox=(card.dataset.caseFocusBbox||'').split(',').map(Number);if(bbox.length!==4||bbox.some(v=>!Number.isFinite(v)))return;const [pw,ph]=pageDimensions(page),rect=stage.getBoundingClientRect();if(!(pw>0&&ph>0&&rect.width>0&&rect.height>0))return;const fit=Math.min(rect.width/pw,rect.height/ph),ox=(rect.width-pw*fit)/2,oy=(rect.height-ph*fit)/2,[l,t,r,b]=bbox,bw=Math.max(1,(r-l)*fit),bh=Math.max(1,(b-t)*fit),target=Math.min(5,Math.max(1,Math.min(rect.width*.58/bw,rect.height*.58/bh))),cx=ox+((l+r)/2)*fit,cy=oy+((t+b)/2)*fit,s=state(stage);s.scale=target;s.x=rect.width/2-cx*target;s.y=rect.height/2-cy*target;apply(stage)})}function ensureReferenceRaster(scope){if(!scope)return;scope.querySelectorAll('[data-reference-page-image]').forEach(image=>{if(image.getAttribute('href'))return;const src=image.dataset.referencePageSrc||'';if(src)image.setAttribute('href',src)})}const referenceStates=new WeakMap();function referenceState(stage){let s=referenceStates.get(stage);if(!s){s={scale:1,x:0,y:0,drag:false,px:0,py:0};referenceStates.set(stage,s)}return s}function applyReference(stage){const s=referenceState(stage),t=stage.querySelector('[data-reference-transform]');if(t)t.style.transform=`translate(${s.x}px,${s.y}px) scale(${s.scale})`;syncViews(stage,true)}function resetReference(stage){referenceStates.set(stage,{scale:1,x:0,y:0,drag:false,px:0,py:0});applyReference(stage)}function selectReference(scope,item,load=true){scope.querySelectorAll('[data-reference-role]').forEach(node=>{node.hidden=node!==item;node.classList.toggle('is-active',node===item)});scope.querySelectorAll('details.related-reference').forEach(details=>details.open=true);if(item&&load)ensureReferenceRaster(item)}
refs.forEach(ref=>{const items=[...ref.querySelectorAll('[data-reference-role]')];if(!items.length)return;const label=document.createElement('label');label.className='reference-selector';label.textContent='원문 선택';const select=document.createElement('select');select.setAttribute('aria-label','비교 원문 선택');items.forEach((item,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=(item.dataset.referenceRole==='direct'?'직접 근거 · ':'관련 자료 · ')+(item.querySelector('.reference-anchor-source')?.textContent||'원문 '+(index+1));select.append(option)});label.append(select);ref.prepend(label);select.addEventListener('change',()=>{const item=items[Number(select.value)];selectReference(ref,item);const stage=item?.querySelector('[data-reference-stage]');if(stage)resetReference(stage)});selectReference(ref,items[0],false)});
root.querySelector('[data-comparison-fullscreen]')?.addEventListener('click',async()=>{try{if(document.fullscreenElement===root)await document.exitFullscreen();else await root.requestFullscreen()}catch(_){root.scrollIntoView({block:'start'})}});document.addEventListener('fullscreenchange',()=>{const button=root.querySelector('[data-comparison-fullscreen]');if(button)button.textContent=document.fullscreenElement===root?'전체 화면 닫기':'비교 화면 전체 보기'});
root.querySelector('[data-findings-toggle]')?.addEventListener('click',event=>{const button=event.currentTarget,collapsed=root.dataset.findingsCollapsed!=='true';root.dataset.findingsCollapsed=String(collapsed);button.setAttribute('aria-expanded',String(!collapsed));button.textContent='관찰 '+(button.dataset.findingsCount||cards.length)+' · '+(collapsed?'목록 펼치기':'목록 접기')});
function syncViews(source,isReference){if(!root.querySelector('[data-view-sync]')?.checked)return;const target=isReference?pages[pageIndex]?.querySelector('[data-case-stage]'):root.querySelector('.reference-focus.is-active .reference-viewer-item.is-active [data-reference-stage]');if(!target)return;const a=source.getBoundingClientRect(),b=target.getBoundingClientRect();if(!a.width||!a.height||!b.width||!b.height)return;const from=isReference?referenceState(source):state(source),to=isReference?state(target):referenceState(target);to.scale=from.scale;to.x=from.x*b.width/a.width;to.y=from.y*b.height/a.height;const transform=target.querySelector(isReference?'[data-case-transform]':'[data-reference-transform]');if(transform)transform.style.transform=`translate(${to.x}px,${to.y}px) scale(${to.scale})`;if(isReference){if(zoomLabel)zoomLabel.textContent=`${Math.round(to.scale*100)}%`;scheduleVisibleTiles(pages[pageIndex])}}
function preferredReferenceItem(scope){return scope.querySelector('[data-reference-role].is-active')||scope.querySelector('[data-reference-role="direct"]')||scope.querySelector('[data-reference-role="related"]')}function focusReferenceFinding(scope){if(!scope)return;const item=preferredReferenceItem(scope);if(!item)return;const details=item.closest('details');if(details)details.open=true;const stage=item.querySelector('[data-reference-stage]'),anchor=item.querySelector('[data-reference-anchor]');if(!stage||!anchor)return;requestAnimationFrame(()=>{const pw=Number(stage.dataset.pageWidth||0),ph=Number(stage.dataset.pageHeight||0),rect=stage.getBoundingClientRect(),x=Number(anchor.getAttribute('x')),y=Number(anchor.getAttribute('y')),w=Number(anchor.getAttribute('width')),h=Number(anchor.getAttribute('height'));if(!(pw>0&&ph>0&&rect.width>0&&rect.height>0&&[x,y,w,h].every(Number.isFinite)))return;const fit=Math.min(rect.width/pw,rect.height/ph),ox=(rect.width-pw*fit)/2,oy=(rect.height-ph*fit)/2,bw=Math.max(1,w*fit),bh=Math.max(1,h*fit),target=Math.min(5,Math.max(1,Math.min(rect.width*.58/bw,rect.height*.58/bh))),cx=ox+(x+w/2)*fit,cy=oy+(y+h/2)*fit,s=referenceState(stage);s.scale=target;s.x=rect.width/2-cx*target;s.y=rect.height/2-cy*target;applyReference(stage)})}function referenceZoom(stage,factor,clientX,clientY){if(!stage)return;const s=referenceState(stage),rect=stage.getBoundingClientRect(),cx=clientX??rect.left+rect.width/2,cy=clientY??rect.top+rect.height/2,lx=(cx-rect.left-s.x)/s.scale,ly=(cy-rect.top-s.y)/s.scale,next=Math.min(5,Math.max(.5,s.scale*factor));s.x=cx-rect.left-lx*next;s.y=cy-rect.top-ly*next;s.scale=next;applyReference(stage)}function activateCard(index,{focus=true}={}){if(index<0||index>=cards.length)return;activeCardIndex=index;const selected=root.querySelector('[data-selected-observation]');if(selected)selected.textContent='관찰 '+String(index+1).padStart(2,'0')+' · '+(cards[index].querySelector('h3')?.textContent||'')+' · '+(cards[index].querySelector('.finding-status')?.textContent||'');const card=cards[index],id=card.dataset.caseFinding||'',ids=candidateIds(card);cards.forEach((item,i)=>item.classList.toggle('is-active',i===index));refs.forEach(ref=>{const on=ref.dataset.caseReference===id;ref.hidden=!on;ref.classList.toggle('is-active',on);if(on){const item=preferredReferenceItem(ref);selectReference(ref,item);if(item&&focus)focusReferenceFinding(ref)}});overlays.forEach(overlay=>overlay.classList.toggle('is-active',ids.has(overlay.dataset.caseOverlay||'')));if(focus)focusSubjectFinding(card)}function filteredCardIndexes(){return cards.map((card,index)=>({card,index})).filter(({card})=>filter==='all'||card.dataset.findingStatus===filter).map(({index})=>index)}function renderResultPage({activate=true}={}){const indexes=filteredCardIndexes(),total=Math.max(1,Math.ceil(indexes.length/PAGE_SIZE));resultPage=Math.max(0,Math.min(resultPage,total-1));const slice=new Set(indexes.slice(resultPage*PAGE_SIZE,(resultPage+1)*PAGE_SIZE));cards.forEach((card,index)=>{card.hidden=!slice.has(index)});if(resultPageNo)resultPageNo.textContent=String(resultPage+1);if(resultPageTotal)resultPageTotal.textContent=String(total);const empty=root.querySelector('[data-findings-empty]');if(empty)empty.hidden=indexes.length>0;if(!indexes.length){cards.forEach(c=>c.classList.remove('is-active'));overlays.forEach(o=>o.classList.remove('is-active'))}if(activate&&indexes.length){const preferred=slice.has(activeCardIndex)?activeCardIndex:indexes[resultPage*PAGE_SIZE];activateCard(preferred,{focus:true})}}cards.forEach((card,index)=>card.addEventListener('click',()=>activateCard(index,{focus:true})));filterButtons.forEach(button=>button.addEventListener('click',()=>{filter=button.dataset.caseFilter||'all';filterButtons.forEach(item=>item.classList.toggle('is-active',item===button));resultPage=0;renderResultPage({activate:true})}));root.querySelector('[data-finding-prev]')?.addEventListener('click',()=>{resultPage--;renderResultPage({activate:true})});root.querySelector('[data-finding-next]')?.addEventListener('click',()=>{resultPage++;renderResultPage({activate:true})});root.querySelector('[data-case-prev]')?.addEventListener('click',()=>showPage(pages[(pageIndex-1+pages.length)%pages.length]?.dataset.casePage||''));root.querySelector('[data-case-next]')?.addEventListener('click',()=>showPage(pages[(pageIndex+1)%pages.length]?.dataset.casePage||''));root.querySelectorAll('[data-case-overlay-mode]').forEach(button=>button.addEventListener('click',()=>{const mode=button.dataset.caseOverlayMode||'all';root.dataset.overlayMode=mode;root.querySelectorAll('[data-case-overlay-mode]').forEach(item=>item.classList.toggle('is-active',item===button))}));function zoom(factor,clientX,clientY){const stage=pages[pageIndex]?.querySelector('[data-case-stage]');if(!stage)return;const s=state(stage),rect=stage.getBoundingClientRect(),cx=clientX??rect.left+rect.width/2,cy=clientY??rect.top+rect.height/2,lx=(cx-rect.left-s.x)/s.scale,ly=(cy-rect.top-s.y)/s.scale,next=Math.min(5,Math.max(.5,s.scale*factor));s.x=cx-rect.left-lx*next;s.y=cy-rect.top-ly*next;s.scale=next;apply(stage)}root.querySelector('[data-case-zoom-in]')?.addEventListener('click',()=>zoom(1.2));root.querySelector('[data-case-zoom-out]')?.addEventListener('click',()=>zoom(.8333));root.querySelector('[data-case-fit-screen]')?.addEventListener('click',()=>fitScreen(pages[pageIndex]?.querySelector('[data-case-stage]')));root.querySelector('[data-case-fit-width]')?.addEventListener('click',()=>fitWidth(pages[pageIndex]?.querySelector('[data-case-stage]')));root.querySelector('[data-case-original-size]')?.addEventListener('click',()=>originalSize(pages[pageIndex]?.querySelector('[data-case-stage]')));root.querySelectorAll('[data-reference-expand]').forEach(button=>{let dialog=null,placeholder=null;button.addEventListener('click',()=>{const item=button.closest('.reference-viewer-item'),stage=item?.querySelector('[data-reference-stage]');if(!item||!stage)return;if(dialog){dialog.close();placeholder.replaceWith(item);dialog.remove();dialog=null;placeholder=null;item.classList.remove('reference-expanded');button.setAttribute('aria-expanded','false');button.textContent='원문 크게 보기';resetReference(stage);button.focus();return}placeholder=document.createComment('reference viewer position');item.before(placeholder);dialog=document.createElement('dialog');dialog.className='reference-lightbox';dialog.setAttribute('aria-label','기준 원문 크게 보기');root.append(dialog);dialog.append(item);item.classList.add('reference-expanded');button.setAttribute('aria-expanded','true');button.textContent='원문 크게 보기 닫기';dialog.addEventListener('cancel',e=>{e.preventDefault();button.click()});dialog.showModal();ensureReferenceRaster(item);resetReference(stage);button.focus()})});root.querySelectorAll('[data-reference-zoom]').forEach(button=>button.addEventListener('click',()=>{const stage=button.closest('.reference-viewer-item')?.querySelector('[data-reference-stage]');if(!stage)return;ensureReferenceRaster(button.closest('.reference-viewer-item'));if(button.dataset.referenceZoom==='fit')resetReference(stage);else referenceZoom(stage,button.dataset.referenceZoom==='in'?1.3:1/1.3)}));root.querySelectorAll('[data-reference-stage]').forEach(stage=>{stage.addEventListener('keydown',e=>{if(e.key==='Escape'){stage.closest('.reference-expanded')?.querySelector('[data-reference-expand]')?.click()}if(e.key==='+'||e.key==='='){e.preventDefault();referenceZoom(stage,1.2)}if(e.key==='-'){e.preventDefault();referenceZoom(stage,.8333)}});stage.addEventListener('wheel',e=>{e.preventDefault();referenceZoom(stage,e.deltaY<0?1.12:.89,e.clientX,e.clientY)},{passive:false});stage.addEventListener('dblclick',()=>resetReference(stage));stage.addEventListener('pointerdown',e=>{if(e.button!==0)return;const s=referenceState(stage);s.drag=true;s.px=e.clientX;s.py=e.clientY;stage.setPointerCapture(e.pointerId);stage.classList.add('is-dragging')});stage.addEventListener('pointermove',e=>{const s=referenceState(stage);if(!s.drag)return;s.x+=e.clientX-s.px;s.y+=e.clientY-s.py;s.px=e.clientX;s.py=e.clientY;applyReference(stage)});const stop=e=>{referenceState(stage).drag=false;stage.classList.remove('is-dragging');try{stage.releasePointerCapture(e.pointerId)}catch(_){}};stage.addEventListener('pointerup',stop);stage.addEventListener('pointercancel',stop)});pages.forEach(page=>{const stage=page.querySelector('[data-case-stage]');if(!stage)return;stage.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.12:.89,e.clientX,e.clientY)},{passive:false});stage.addEventListener('dblclick',()=>reset(stage));stage.addEventListener('pointerdown',e=>{if(e.button!==0)return;const s=state(stage);s.drag=true;s.px=e.clientX;s.py=e.clientY;stage.setPointerCapture(e.pointerId);stage.classList.add('is-dragging')});stage.addEventListener('pointermove',e=>{const s=state(stage);if(!s.drag)return;s.x+=e.clientX-s.px;s.y+=e.clientY-s.py;s.px=e.clientX;s.py=e.clientY;apply(stage)});const stop=e=>{state(stage).drag=false;stage.classList.remove('is-dragging');try{stage.releasePointerCapture(e.pointerId)}catch(_){}};stage.addEventListener('pointerup',stop);stage.addEventListener('pointercancel',stop)});const split=root.querySelector('[data-case-split]'),divider=root.querySelector('[data-case-divider]');function setSplit(percent){if(!split||!divider)return;const value=Math.min(70,Math.max(26,percent));split.style.setProperty('--reference-width',`${value}%`);divider.setAttribute('aria-valuenow',String(Math.round(value)))}if(split&&divider){let dragging=false;divider.addEventListener('pointerdown',e=>{if(e.button!==0)return;dragging=true;divider.setPointerCapture(e.pointerId)});divider.addEventListener('pointermove',e=>{if(!dragging)return;const rect=split.getBoundingClientRect();setSplit((e.clientX-rect.left)/rect.width*100)});const stop=e=>{dragging=false;try{divider.releasePointerCapture(e.pointerId)}catch(_){}};divider.addEventListener('pointerup',stop);divider.addEventListener('pointercancel',stop);divider.addEventListener('dblclick',()=>setSplit(50));divider.addEventListener('keydown',e=>{const now=Number(divider.getAttribute('aria-valuenow')||50);if(e.key==='ArrowLeft'){e.preventDefault();setSplit(now-2)}if(e.key==='ArrowRight'){e.preventDefault();setSplit(now+2)}})}let decisionTrigger=null;function setDecision(open,trigger){document.body.dataset.visualDecisionOpen=open?'true':'false';const backdrop=root.querySelector('[data-case-decision-surface]');if(backdrop)backdrop.hidden=!open;const form=document.getElementById('decision-form');if(!form)return;if(open){decisionTrigger=trigger||root.querySelector('[data-case-decision-trigger]');form.setAttribute('aria-hidden','false');let close=form.querySelector('[data-visual-decision-close]');if(!close){close=document.createElement('button');close.type='button';close.dataset.visualDecisionClose='';close.className='visual-decision-close';close.textContent='Close';form.prepend(close);close.addEventListener('click',()=>setDecision(false))}form.querySelector('input,textarea,button')?.focus();return}form.setAttribute('aria-hidden','true');decisionTrigger?.focus();decisionTrigger=null}const decisionForm=document.getElementById('decision-form');if(decisionForm && !decisionForm.closest('[data-review-shell="unified"]'))decisionForm.setAttribute('aria-hidden','true');root.querySelector('[data-case-decision-trigger]')?.addEventListener('click',event=>setDecision(true,event.currentTarget));root.querySelector('[data-case-decision-surface]')?.addEventListener('click',()=>setDecision(false));document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.dataset.visualDecisionOpen==='true')setDecision(false)});showPage(pages[0]?.dataset.casePage||'');fitWidth(pages[0]?.querySelector('[data-case-stage]'));renderResultPage({activate:false});if(cards.length)activateCard(0,{focus:false})})();
