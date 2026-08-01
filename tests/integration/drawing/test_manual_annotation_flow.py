from pathlib import Path

from ansim_review.contracts.drawing import DrawingConfirmation, Geometry
from ansim_review.parsing.drawing_binding import bind_confirmed_inputs
from ansim_review.parsing.drawing_candidates import (
    create_manual_candidate,
    persist_candidate,
)
from ansim_review.parsing.drawing_case import (
    CaseManifest,
    case_manifest_document,
    write_canonical_create_only,
)
from ansim_review.parsing.drawing_confirmation import persist_confirmation
from ansim_review.parsing.drawing_inputs import (
    ConfirmedInputBuildRequest,
    build_confirmed_input,
    persist_confirmed_inputs,
)
from ansim_review.parsing.drawing_quality import (
    TrustedSourceMetadata,
    assess_drawing_quality,
    persist_drawing_quality,
)
from ansim_review.parsing.drawing_source import (
    DrawingIntakePolicy,
    drawing_source_manifest_entry,
    ingest_drawing_source,
)
from ansim_review.parsing.drawing_workflow import (
    DrawingWorkflowFacts,
    project_drawing_workflow,
)


def test_manual_annotation_reaches_ready_to_evaluate(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    source = tmp_path / "site-plan.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fixture")
    policy = DrawingIntakePolicy()

    attachment = ingest_drawing_source(
        source, case_dir, "ATT-001", "CASE_DRAWING", policy
    )
    source_entry = drawing_source_manifest_entry(attachment)
    quality = assess_drawing_quality(
        attachment,
        TrustedSourceMetadata(
            source_sha256=attachment.sha256,
            adapter="fixture",
            adapter_version="1",
            parser_outcome="SUCCESS",
            page_count=None,
            width=4000,
            height=3000,
            physical_size_trust="USER_CONFIRMED",
            lossy_or_screen_capture=False,
        ),
        policy,
    )
    assert quality.assessment.quality == "PASS"
    quality_entry = persist_drawing_quality(
        case_dir, attachment.attachment_id, attachment.sha256, quality
    )

    candidate = create_manual_candidate(
        case_id="CASE-001",
        source_sha256=attachment.sha256,
        page=1,
        annotation_id="ANN-ROAD-WIDTH",
        candidate_type="ROAD_WIDTH_TEXT",
        geometry=Geometry(
            type="LINESTRING",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=((100.0, 200.0), (900.0, 200.0)),
        ),
        raw_value=None,
        normalized_candidate=None,
    )
    candidate_entry = persist_candidate(case_dir, candidate)

    confirmation = DrawingConfirmation(
        confirmation_id="CONF-001",
        candidate_id=candidate.candidate_id,
        action="CREATED",
        source_sha256=attachment.sha256,
        reviewer="김성현",
        confirmed_at="2026-08-02T01:30:00+09:00",
        confirmed_value="8.0",
        unit="m",
        geometry=None,
    )
    confirmation_entry = persist_confirmation(
        case_dir, "kim-sh", candidate, confirmation
    )
    confirmed = build_confirmed_input(
        ConfirmedInputBuildRequest(
            input_id="INPUT-ROAD-WIDTH",
            field="road_width_m",
            value="8.0",
            unit="m",
            candidate=candidate,
            effective_status="CREATED",
            confirmation=confirmation,
            confirmation_entry=confirmation_entry,
        )
    )
    confirmed_entry = persist_confirmed_inputs(case_dir, [confirmed])

    bound = bind_confirmed_inputs(
        case_dir,
        [confirmed],
        {attachment.sha256: attachment},
    )
    assert bound["road_width_m"].value == "8.0"

    workflow = project_drawing_workflow(
        "RUN-001",
        DrawingWorkflowFacts(has_source=True, has_validated_inputs=True),
    )
    assert workflow.workflow_state == "READY_TO_EVALUATE"

    manifest = CaseManifest(
        format="ansim/case-manifest",
        version=1,
        case_id="CASE-001",
        policy_id=policy.policy_id,
        sources=(source_entry,),
        quality_assessments=(quality_entry,),
        candidates=(candidate_entry,),
        confirmations=(confirmation_entry,),
        confirmed_inputs_path=confirmed_entry.relative_path,
        confirmed_inputs_sha256=confirmed_entry.sha256,
    )
    write_canonical_create_only(
        case_dir / "manifest.json",
        case_manifest_document(manifest),
    )
    assert (case_dir / "manifest.json").is_file()
