(function () {
  "use strict";

  const modelNode = document.getElementById("review-model");
  const reviewModel = modelNode ? JSON.parse(modelNode.textContent || "{}") : {};

  function formStatus(message) {
    const status = document.querySelector(".form-status");
    if (status) status.textContent = message;
  }

  function decisionEnvelope(form) {
    const values = new FormData(form);
    return {
      reviewer_id: values.get("reviewer_id") || "",
      reviewed_at: values.get("reviewed_at") || "",
      packet_hash: values.get("packet_sha256") || "",
      decision: values.get("decision") || "",
      notes: values.get("notes") || ""
    };
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
    panels.forEach((panel) => {
      panel.hidden = false;
    });
  }

  function restorePrintPanels() {
    if (printPanelStates === null) return;
    printPanelStates.forEach((state) => {
      state.panel.hidden = state.hidden;
    });
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
    if (page) {
      page.scrollIntoView({ behavior: "smooth", block: "nearest" });
      page.focus({ preventScroll: true });
    }
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
    if (!form.reportValidity()) return;
    formStatus("검토자 결정을 로컬 엔드포인트로 전송하는 중입니다.");
    try {
      const response = await fetch("./decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(decisionEnvelope(form))
      });
      formStatus(response.ok ? "결정이 별도 기록으로 저장되었습니다." : "결정 엔드포인트가 제출을 거부했습니다.");
    } catch (_) {
      formStatus("보관 HTML에서는 로컬 결정 엔드포인트를 사용할 수 없습니다.");
    }
  }

  function downloadDecisionEnvelope() {
    const form = document.querySelector("#decision-form form");
    if (!form || !form.reportValidity()) return;
    const blob = new Blob([JSON.stringify(decisionEnvelope(form), null, 2)], {
      type: "application/json"
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "human-decision-envelope.json";
    link.click();
    URL.revokeObjectURL(link.href);
    formStatus("별도의 결정 JSON을 다운로드했습니다.");
  }

  window.selectReviewItem = selectReviewItem;
  window.activateDetailTab = activateDetailTab;
  window.focusEvidence = focusEvidence;
  window.setEvidenceZoom = setEvidenceZoom;
  window.submitDecision = submitDecision;
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

  void reviewModel;
}());
