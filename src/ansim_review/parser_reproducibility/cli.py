"""Create-only CLI handlers for parser reproducibility evidence."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.parser_reproducibility.contract import (
    decode_reproducibility_config,
)
from ansim_review.parser_reproducibility.queue import decode_review_queue
from ansim_review.parser_reproducibility.report import (
    collect_opendataloader_warnings,
    report_bytes,
    validate_opendataloader_reproducibility,
)
from ansim_review.parser_reproducibility.run_manifest import (
    read_parser_run_metadata,
)
from ansim_review.parser_reproducibility.source_identity import (
    SourceIdentityAuthorityError,
    resolve_source_identity,
)


def reserve_outputs(paths: Sequence[Path]) -> tuple[int, ...]:
    """Reserve every output with exclusive creation or roll back all paths."""

    descriptors: list[int] = []
    reserved: list[Path] = []
    try:
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            descriptors.append(descriptor)
            reserved.append(path)
        return tuple(descriptors)
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        for path in reserved:
            path.unlink(missing_ok=True)
        raise


def _write_reserved(
    paths: Sequence[Path],
    descriptors: Sequence[int],
    payloads: Sequence[bytes],
) -> None:
    if not (len(paths) == len(descriptors) == len(payloads)):
        raise ValueError("reserved output counts do not match")
    try:
        for descriptor, payload in zip(descriptors, payloads, strict=True):
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        for path in paths:
            path.unlink(missing_ok=True)
        raise


def _stdout(document: object) -> None:
    sys.stdout.buffer.write(dump_bytes(document) + b"\n")


def validate_command(
    source: Path,
    run_a: Path,
    run_b: Path,
    config_path: Path,
    output: Path,
) -> int:
    """Run two-run validation and write one canonical report."""

    try:
        config = decode_reproducibility_config(config_path.read_bytes())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        descriptors = reserve_outputs((output,))
    except (FileExistsError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        report = validate_opendataloader_reproducibility(
            source,
            run_a,
            run_b,
            config,
        )
        _write_reserved((output,), descriptors, (report_bytes(report),))
    except BaseException:
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        output.unlink(missing_ok=True)
        raise
    _stdout(
        {
            "format": "evidence-review/parser-reproducibility-cli-status",
            "version": 1,
            "status": report.status,
            "difference_count": len(report.differences),
            "error_count": report.error_count,
            "warning_count": report.warning_count,
        }
    )
    if report.status in {"BYTE_IDENTICAL", "SEMANTICALLY_IDENTICAL"}:
        return 0
    if report.status == "MISMATCH":
        return 1
    if report.status == "ENVIRONMENT_MISMATCH":
        return 2
    return 3


def _warning_authority(
    source_manifest: Path,
    parser_artifacts: Path,
):
    try:
        metadata = read_parser_run_metadata(parser_artifacts)
    except FileNotFoundError as exc:
        raise SourceIdentityAuthorityError(
            "PARSER_RUN_AUTHORITY_MISSING"
        ) from exc
    except (OSError, ValueError) as exc:
        raise SourceIdentityAuthorityError(
            "PARSER_RUN_AUTHORITY_INVALID"
        ) from exc
    return resolve_source_identity(source_manifest, metadata)


def collect_warnings_command(
    source_manifest: Path,
    parser_artifacts: Path,
    config_path: Path,
    warning_output: Path,
    queue_output: Path,
    previous_queue_path: Path | None,
) -> int:
    """Collect warnings and atomically write warning and queue reports."""

    try:
        config = decode_reproducibility_config(config_path.read_bytes())
        previous = (
            None
            if previous_queue_path is None
            else decode_review_queue(previous_queue_path.read_bytes())
        )
        source_identity = _warning_authority(
            source_manifest,
            parser_artifacts,
        )
    except SourceIdentityAuthorityError as exc:
        print(exc.code, file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    paths = (warning_output, queue_output)
    try:
        descriptors = reserve_outputs(paths)
    except (FileExistsError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        result = collect_opendataloader_warnings(
            source_identity,
            parser_artifacts,
            config,
            previous,
        )
        _write_reserved(
            paths,
            descriptors,
            (
                report_bytes(result.warning_report),
                report_bytes(result.review_queue),
            ),
        )
    except (OSError, ValueError) as exc:
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        for path in paths:
            path.unlink(missing_ok=True)
        print(str(exc), file=sys.stderr)
        return 3
    _stdout(
        {
            "format": "evidence-review/parser-warning-cli-status",
            "version": 1,
            "status": "COLLECTED",
            "warning_count": len(result.warning_report.warnings),
            "queue_count": len(result.review_queue.entries),
        }
    )
    return 0
