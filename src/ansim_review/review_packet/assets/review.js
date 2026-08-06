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
      run_id: reviewModel.run_id,
      reviewer_id: values.get("reviewer_id") || "",
      reviewed_at: values.get("reviewed_at") || "",
      packet_hash: values.get("packet_sha256") || "",
      decision: values.get("decision") || "",
      notes: values.get("notes") || ""
    };
  }

  function selectReviewItem(itemId) {
    document.querySelectorAll(".review-item, .detail-panel").forEach((node) => {
      const selected = node.dataset.itemId === itemId;
      node.classList.toggle("is-selected", selected);
      if (node.classList.contains("review-item")) {
        node.setAttribute("aria-pressed", selected ? "true" : "false");
      }
    });
  }

  function activateDetailTab(tabName) {
    document.querySelectorAll("[data-detail-tab]").forEach((tab) => {
      tab.setAttribute("aria-selected", tab.dataset.detailTab === tabName ? "true" : "false");
    });
    document.querySelectorAll(".detail-panel [data-tab-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.tabPanel !== tabName;
    });
  }

  function focusEvidence(assetKey) {
    document.querySelectorAll(".evidence-page").forEach((page) => {
      page.classList.toggle("is-active", page.dataset.assetKey === assetKey);
    });
    const page = document.querySelector('.evidence-page[data-asset-key="' + assetKey + '"]');
    if (page) {
      page.scrollIntoView({ behavior: "smooth", block: "nearest" });
      page.focus({ preventScroll: true });
    }
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
    formStatus("Submitting reviewer-entered decision to the local endpoint…");
    try {
      const response = await fetch("./decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(decisionEnvelope(form))
      });
      formStatus(response.ok ? "Decision submitted." : "Decision endpoint rejected the submission.");
    } catch (_) {
      formStatus("No local decision endpoint is available in this archival file.");
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
    formStatus("Downloaded a separate decision envelope.");
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
  });
  document.querySelectorAll(".evidence-link").forEach((link) => {
    link.addEventListener("click", () => focusEvidence(link.dataset.assetKey));
  });
  const zoom = document.getElementById("evidence-zoom");
  if (zoom) zoom.addEventListener("input", () => setEvidenceZoom(zoom.value));
  const form = document.querySelector("#decision-form form");
  if (form) form.addEventListener("submit", submitDecision);
  const download = document.querySelector("[data-download-decision]");
  if (download) download.addEventListener("click", downloadDecisionEnvelope);
}());
