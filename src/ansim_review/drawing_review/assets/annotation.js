(() => {
  "use strict";

  const buttons = Array.from(document.querySelectorAll("[data-candidate-button]"));
  const geometries = Array.from(document.querySelectorAll(".candidate-geometry"));
  const detailId = document.querySelector("[data-detail-id]");
  const detailType = document.querySelector("[data-detail-type]");
  const detailOrigin = document.querySelector("[data-detail-origin]");
  const detailStatus = document.querySelector("[data-detail-status]");
  const detailValue = document.querySelector("[data-detail-value]");

  function selectCandidate(candidateId) {
    for (const button of buttons) {
      const selected = button.dataset.candidateId === candidateId;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    }
    for (const geometry of geometries) {
      geometry.classList.toggle(
        "is-selected",
        geometry.dataset.candidateId === candidateId,
      );
    }

    const selectedButton = buttons.find(
      (button) => button.dataset.candidateId === candidateId,
    );
    if (!selectedButton) {
      return;
    }
    if (detailId) detailId.textContent = selectedButton.dataset.candidateId || "";
    if (detailType) detailType.textContent = selectedButton.dataset.candidateType || "";
    if (detailOrigin) detailOrigin.textContent = selectedButton.dataset.candidateOrigin || "";
    if (detailStatus) detailStatus.textContent = selectedButton.dataset.candidateStatus || "";
    if (detailValue) detailValue.textContent = selectedButton.dataset.candidateValue || "";
  }

  for (const button of buttons) {
    button.addEventListener("click", () => {
      selectCandidate(button.dataset.candidateId || "");
    });
  }
  for (const geometry of geometries) {
    geometry.addEventListener("click", () => {
      selectCandidate(geometry.dataset.candidateId || "");
    });
  }
})();
