(() => {
  "use strict";

  const buttons = Array.from(document.querySelectorAll("[data-candidate-button]"));
  const geometries = Array.from(document.querySelectorAll(".candidate-geometry"));
  const displayModeButtons = Array.from(
    document.querySelectorAll("[data-display-mode]"),
  );
  const workspaceTabs = Array.from(
    document.querySelectorAll('[role="tab"][data-workspace-tab]'),
  );
  const workspacePanes = Array.from(
    document.querySelectorAll("[data-workspace-pane]"),
  );
  const overlay = document.querySelector("[data-annotation-overlay]");
  const drawingStage = document.querySelector("#drawingStage");
  const selectedObject = document.querySelector("[data-selected-object]");
  const selectedCoordinates = document.querySelector("[data-selected-coordinates]");
  const selectedStatus = document.querySelector("[data-selected-status]");
  const detailId = document.querySelector("[data-detail-id]");
  const detailType = document.querySelector("[data-detail-type]");
  const detailOrigin = document.querySelector("[data-detail-origin]");
  const detailStatus = document.querySelector("[data-detail-status]");
  const detailValue = document.querySelector("[data-detail-value]");
  const reviewer = document.querySelector("[data-reviewer]");
  const confirmedValue = document.querySelector("[data-confirmed-value]");
  const unit = document.querySelector("[data-unit]");
  const annotationId = document.querySelector("[data-annotation-id]");
  const candidateTypeInput = document.querySelector("[data-candidate-type-input]");
  const geometryTool = document.querySelector("[data-geometry-tool]");
  const finishGeometry = document.querySelector("[data-finish-geometry]");
  const clearGeometry = document.querySelector("[data-clear-geometry]");
  const submitAction = document.querySelector("[data-submit-action]");
  const actionStatus = document.querySelector("[data-action-status]");
  const openConfirmation = document.querySelector("[data-open-confirmation]");
  const printWorkspace = document.querySelector("[data-print-workspace]");

  let selectedCandidateId = "";
  let draftDisplayPoints = [];
  let draftGeometry = null;
  let dragStart = null;
  let previewElement = null;

  const coordinateSystem = overlay ? overlay.dataset.coordinateSystem || "" : "";
  const pageHeight = overlay ? Number(overlay.dataset.pageHeight || "0") : 0;

  function setStatus(message) {
    if (actionStatus) actionStatus.textContent = message;
  }

  function setDisplayMode(mode) {
    if (!drawingStage) return;
    drawingStage.classList.remove("mode-original", "mode-detection", "mode-compare");
    drawingStage.classList.add(`mode-${mode}`);
    for (const button of displayModeButtons) {
      const active = button.dataset.displayMode === mode;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  function activateWorkspaceTab(name) {
    for (const tab of workspaceTabs) {
      const active = tab.dataset.workspaceTab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
      tab.tabIndex = active ? 0 : -1;
    }
    for (const pane of workspacePanes) {
      pane.hidden = pane.dataset.workspacePane !== name;
    }
  }

  function geometryDescription(candidateId) {
    const geometry = geometries.find(
      (item) => item.dataset.candidateId === candidateId,
    );
    if (!geometry) return "—";
    const tag = geometry.tagName.toUpperCase();
    if (tag === "CIRCLE") {
      return `점 (${geometry.getAttribute("cx")}, ${geometry.getAttribute("cy")})`;
    }
    if (tag === "RECT") {
      return `사각형 (${geometry.getAttribute("x")}, ${geometry.getAttribute("y")})`;
    }
    const geometryLabel = tag === "POLYLINE" ? "선" : "다각형";
    return `${geometryLabel} ${geometry.getAttribute("points") || ""}`;
  }

  function updateCandidateMetrics(button) {
    if (!button) return;
    if (selectedObject) {
      selectedObject.textContent = button.dataset.candidateTypeLabel || "—";
    }
    if (selectedCoordinates) {
      selectedCoordinates.textContent = geometryDescription(button.dataset.candidateId || "");
    }
    if (selectedStatus) {
      selectedStatus.textContent = button.dataset.candidateStatusLabel || "—";
    }
  }

  function selectCandidate(candidateId) {
    selectedCandidateId = candidateId;
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
    if (!selectedButton) return;
    if (detailId) detailId.textContent = selectedButton.dataset.candidateId || "";
    if (detailType) detailType.textContent = selectedButton.dataset.candidateTypeLabel || "";
    if (detailOrigin) detailOrigin.textContent = selectedButton.dataset.candidateOriginLabel || "";
    if (detailStatus) detailStatus.textContent = selectedButton.dataset.candidateStatusLabel || "";
    if (detailValue) detailValue.textContent = selectedButton.dataset.candidateValue || "";
    updateCandidateMetrics(selectedButton);
  }

  function pointerPosition(event) {
    if (!overlay) throw new Error("도면 주석 오버레이를 사용할 수 없습니다.");
    const matrix = overlay.getScreenCTM();
    if (!matrix) throw new Error("도면 좌표 변환을 사용할 수 없습니다.");
    const sourcePoint = overlay.createSVGPoint();
    sourcePoint.x = event.clientX;
    sourcePoint.y = event.clientY;
    return sourcePoint.matrixTransform(matrix.inverse());
  }

  function canonicalPoint(point) {
    if (coordinateSystem === "PDF_BOTTOM_LEFT_POINTS") {
      return [point.x, pageHeight - point.y];
    }
    return [point.x, point.y];
  }

  function removePreview() {
    if (previewElement) previewElement.remove();
    previewElement = null;
  }

  function createPreview(tagName) {
    removePreview();
    if (!overlay) return null;
    previewElement = document.createElementNS(overlay.namespaceURI, tagName);
    previewElement.classList.add("draft-geometry");
    overlay.append(previewElement);
    return previewElement;
  }

  function pointsAttribute(points) {
    return points.map((point) => `${point.x},${point.y}`).join(" ");
  }

  function renderPoint(point) {
    const element = createPreview("circle");
    if (!element) return;
    element.setAttribute("cx", String(point.x));
    element.setAttribute("cy", String(point.y));
    element.setAttribute("r", "6");
  }

  function renderPath(points, closed) {
    const element = createPreview(closed ? "polygon" : "polyline");
    if (!element) return;
    element.setAttribute("points", pointsAttribute(points));
    if (!closed) element.setAttribute("fill", "none");
  }

  function renderBox(first, second) {
    const element = createPreview("rect");
    if (!element) return;
    const left = Math.min(first.x, second.x);
    const top = Math.min(first.y, second.y);
    element.setAttribute("x", String(left));
    element.setAttribute("y", String(top));
    element.setAttribute("width", String(Math.max(first.x, second.x) - left));
    element.setAttribute("height", String(Math.max(first.y, second.y) - top));
  }

  function clearDraft(message = "임시 형상을 지웠습니다.") {
    draftDisplayPoints = [];
    draftGeometry = null;
    dragStart = null;
    removePreview();
    setStatus(message);
  }

  function finishPathDraft() {
    if (!geometryTool) return;
    const tool = geometryTool.value;
    if (tool === "LINESTRING") {
      if (draftDisplayPoints.length < 2) {
        setStatus("선에는 점이 두 개 이상 필요합니다.");
        return;
      }
      draftGeometry = {
        type: "LINESTRING",
        coordinate_system: coordinateSystem,
        coordinates: draftDisplayPoints.map(canonicalPoint),
      };
      renderPath(draftDisplayPoints, false);
      setStatus("선 형상을 확인할 준비가 됐습니다.");
      return;
    }
    if (tool === "POLYGON") {
      if (draftDisplayPoints.length < 3) {
        setStatus("다각형에는 점이 세 개 이상 필요합니다.");
        return;
      }
      const canonical = draftDisplayPoints.map(canonicalPoint);
      canonical.push(canonical[0]);
      draftGeometry = {
        type: "POLYGON",
        coordinate_system: coordinateSystem,
        coordinates: canonical,
      };
      renderPath(draftDisplayPoints, true);
      setStatus("다각형 형상을 확인할 준비가 됐습니다.");
    }
  }

  function handleOverlayClick(event) {
    if (!overlay || !geometryTool) return;
    const tool = geometryTool.value;
    const point = pointerPosition(event);
    if (tool === "POINT") {
      draftDisplayPoints = [point];
      draftGeometry = {
        type: "POINT",
        coordinate_system: coordinateSystem,
        coordinates: canonicalPoint(point),
      };
      renderPoint(point);
      setStatus("점 형상을 확인할 준비가 됐습니다.");
      return;
    }
    if (tool === "LINESTRING" || tool === "POLYGON") {
      draftDisplayPoints.push(point);
      renderPath(draftDisplayPoints, tool === "POLYGON");
      const toolLabel = tool === "LINESTRING" ? "선" : "다각형";
      setStatus(`${toolLabel}의 ${draftDisplayPoints.length}번째 점을 추가했습니다.`);
    }
  }

  function handlePointerDown(event) {
    if (!overlay || !geometryTool || geometryTool.value !== "BBOX") return;
    dragStart = pointerPosition(event);
    draftDisplayPoints = [dragStart];
    overlay.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event) {
    if (!dragStart || !geometryTool || geometryTool.value !== "BBOX") return;
    renderBox(dragStart, pointerPosition(event));
  }

  function handlePointerUp(event) {
    if (!dragStart || !geometryTool || geometryTool.value !== "BBOX") return;
    const end = pointerPosition(event);
    renderBox(dragStart, end);
    const first = canonicalPoint(dragStart);
    const second = canonicalPoint(end);
    draftGeometry = {
      type: "BBOX",
      coordinate_system: coordinateSystem,
      coordinates: [
        Math.min(first[0], second[0]),
        Math.min(first[1], second[1]),
        Math.max(first[0], second[0]),
        Math.max(first[1], second[1]),
      ],
    };
    draftDisplayPoints = [dragStart, end];
    dragStart = null;
    setStatus("사각형 형상을 확인할 준비가 됐습니다.");
  }

  function nullableValue(input) {
    if (!input) return null;
    const value = input.value.trim();
    return value === "" ? null : value;
  }

  function commonPayload(action, includeConfirmedValue) {
    if (!reviewer || reviewer.value.trim() === "") {
      throw new Error("검토자 ID가 필요합니다.");
    }
    let value = null;
    let selectedUnit = null;
    if (includeConfirmedValue) {
      value = nullableValue(confirmedValue);
      selectedUnit = nullableValue(unit);
      if ((value === null) !== (selectedUnit === null)) {
        throw new Error("확인 값과 단위를 함께 입력해야 합니다.");
      }
    }
    return {
      action,
      reviewer: reviewer.value.trim(),
      confirmed_at: new Date().toISOString(),
      confirmed_value: value,
      unit: selectedUnit,
    };
  }

  function existingActionPayload(action) {
    if (selectedCandidateId === "") {
      throw new Error("후보를 먼저 선택하세요.");
    }
    return {
      ...commonPayload(action, action === "EDITED"),
      candidate_id: selectedCandidateId,
      geometry: action === "EDITED" ? draftGeometry : null,
    };
  }

  function manualCreatePayload() {
    if (!annotationId || annotationId.value.trim() === "") {
      throw new Error("주석 ID가 필요합니다.");
    }
    if (!candidateTypeInput || candidateTypeInput.value.trim() === "") {
      throw new Error("후보 유형이 필요합니다.");
    }
    if (!draftGeometry) {
      throw new Error("저장하기 전에 형상을 만드세요.");
    }
    return {
      ...commonPayload("CREATED", true),
      action: "CREATED",
      annotation_id: annotationId.value.trim(),
      candidate_type: candidateTypeInput.value.trim(),
      geometry: draftGeometry,
    };
  }

  async function submitSelectedAction() {
    const selectedAction = document.querySelector("input[name=review-action]:checked");
    if (!selectedAction) {
      setStatus("검토자 조치를 선택하세요.");
      return;
    }
    try {
      const payload = selectedAction.value === "CREATED"
        ? manualCreatePayload()
        : existingActionPayload(selectedAction.value);
      const response = await fetch(window.location.pathname + "/actions", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error("작업에 실패했습니다.");
      }
      for (const radio of document.querySelectorAll("input[name=review-action]")) {
        radio.checked = false;
      }
      clearDraft("");
      setStatus(`확인 기록을 저장했습니다. (${result.confirmation.artifact_id})`);
    } catch (error) {
      const message = error instanceof Error && /[가-힣]/.test(error.message)
        ? error.message
        : "작업에 실패했습니다. 입력과 서버 상태를 확인하세요.";
      setStatus(message);
    }
  }

  for (const button of buttons) {
    button.addEventListener("click", () => {
      selectCandidate(button.dataset.candidateId || "");
    });
  }
  for (const geometry of geometries) {
    geometry.addEventListener("click", (event) => {
      event.stopPropagation();
      selectCandidate(geometry.dataset.candidateId || "");
    });
  }
  for (const button of displayModeButtons) {
    button.addEventListener("click", () => {
      setDisplayMode(button.dataset.displayMode || "detection");
    });
  }
  for (const tab of workspaceTabs) {
    tab.addEventListener("click", () => {
      activateWorkspaceTab(tab.dataset.workspaceTab || "evidence");
    });
  }
  if (openConfirmation) {
    openConfirmation.addEventListener("click", () => {
      activateWorkspaceTab("confirmation");
      const reviewPanel = document.querySelector("#reviewer-action");
      if (reviewPanel) reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  if (overlay) {
    overlay.addEventListener("click", handleOverlayClick);
    overlay.addEventListener("pointerdown", handlePointerDown);
    overlay.addEventListener("pointermove", handlePointerMove);
    overlay.addEventListener("pointerup", handlePointerUp);
  }
  if (finishGeometry) finishGeometry.addEventListener("click", finishPathDraft);
  if (clearGeometry) clearGeometry.addEventListener("click", () => clearDraft());
  if (geometryTool) geometryTool.addEventListener("change", () => clearDraft());
  if (submitAction) submitAction.addEventListener("click", submitSelectedAction);
  if (printWorkspace) printWorkspace.addEventListener("click", () => window.print());
})();
