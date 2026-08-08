(() => {
  "use strict";

  const buttons = Array.from(document.querySelectorAll("[data-candidate-button]"));
  const geometries = Array.from(document.querySelectorAll(".candidate-geometry"));
  const displayModeButtons = Array.from(
    document.querySelectorAll("[data-display-mode]"),
  );
  const workspaceTabs = Array.from(
    document.querySelectorAll("[data-workspace-tab]"),
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
      return `POINT (${geometry.getAttribute("cx")}, ${geometry.getAttribute("cy")})`;
    }
    if (tag === "RECT") {
      return `BBOX (${geometry.getAttribute("x")}, ${geometry.getAttribute("y")})`;
    }
    return `${tag} ${geometry.getAttribute("points") || ""}`;
  }

  function updateCandidateMetrics(button) {
    if (!button) return;
    if (selectedObject) {
      selectedObject.textContent = button.dataset.candidateType || "—";
    }
    if (selectedCoordinates) {
      selectedCoordinates.textContent = geometryDescription(button.dataset.candidateId || "");
    }
    if (selectedStatus) {
      selectedStatus.textContent = button.dataset.candidateStatus || "—";
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
    if (detailType) detailType.textContent = selectedButton.dataset.candidateType || "";
    if (detailOrigin) detailOrigin.textContent = selectedButton.dataset.candidateOrigin || "";
    if (detailStatus) detailStatus.textContent = selectedButton.dataset.candidateStatus || "";
    if (detailValue) detailValue.textContent = selectedButton.dataset.candidateValue || "";
    updateCandidateMetrics(selectedButton);
  }

  function pointerPosition(event) {
    if (!overlay) throw new Error("annotation overlay is unavailable");
    const matrix = overlay.getScreenCTM();
    if (!matrix) throw new Error("annotation transform is unavailable");
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

  function clearDraft(message = "Draft geometry cleared.") {
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
        setStatus("LINESTRING requires at least two points.");
        return;
      }
      draftGeometry = {
        type: "LINESTRING",
        coordinate_system: coordinateSystem,
        coordinates: draftDisplayPoints.map(canonicalPoint),
      };
      renderPath(draftDisplayPoints, false);
      setStatus("LINESTRING geometry is ready.");
      return;
    }
    if (tool === "POLYGON") {
      if (draftDisplayPoints.length < 3) {
        setStatus("POLYGON requires at least three points.");
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
      setStatus("POLYGON geometry is ready.");
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
      setStatus("POINT geometry is ready.");
      return;
    }
    if (tool === "LINESTRING" || tool === "POLYGON") {
      draftDisplayPoints.push(point);
      renderPath(draftDisplayPoints, tool === "POLYGON");
      setStatus(`${tool} point ${draftDisplayPoints.length} added.`);
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
    setStatus("BBOX geometry is ready.");
  }

  function nullableValue(input) {
    if (!input) return null;
    const value = input.value.trim();
    return value === "" ? null : value;
  }

  function commonPayload(action, includeConfirmedValue) {
    if (!reviewer || reviewer.value.trim() === "") {
      throw new Error("Reviewer ID is required.");
    }
    let value = null;
    let selectedUnit = null;
    if (includeConfirmedValue) {
      value = nullableValue(confirmedValue);
      selectedUnit = nullableValue(unit);
      if ((value === null) !== (selectedUnit === null)) {
        throw new Error("Confirmed value and unit must be entered together.");
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
      throw new Error("Select a candidate first.");
    }
    return {
      ...commonPayload(action, action === "EDITED"),
      candidate_id: selectedCandidateId,
      geometry: action === "EDITED" ? draftGeometry : null,
    };
  }

  function manualCreatePayload() {
    if (!annotationId || annotationId.value.trim() === "") {
      throw new Error("Annotation ID is required.");
    }
    if (!candidateTypeInput || candidateTypeInput.value.trim() === "") {
      throw new Error("Candidate type is required.");
    }
    if (!draftGeometry) {
      throw new Error("Create geometry before submitting.");
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
      setStatus("Select a reviewer action.");
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
        throw new Error(result.error || "Action failed.");
      }
      for (const radio of document.querySelectorAll("input[name=review-action]")) {
        radio.checked = false;
      }
      clearDraft("");
      setStatus(`Saved confirmation ${result.confirmation.artifact_id}.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Action failed.");
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
      if (tab.classList.contains("secondary-action")) {
        const reviewPanel = document.querySelector("#reviewer-action");
        if (reviewPanel) reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
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
})();
