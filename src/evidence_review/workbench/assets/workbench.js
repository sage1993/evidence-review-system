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

  document.querySelectorAll("[data-evidence-reference]").forEach((button) => {
    button.addEventListener("click", () => focusProvenance(button));
  });
  const formalize = document.querySelector("[data-workbench-formalize]");
  if (formalize) formalize.addEventListener("click", () => requestFormalization(formalize));
}());
