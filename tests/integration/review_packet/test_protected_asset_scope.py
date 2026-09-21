from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from threading import Thread

from PIL import Image

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_packet.local_server import create_review_server
from tests.integration.abstention.test_finalizer import _write_run
from tests.integration.review_packet.test_protected_image_delivery import _get
from tests.integration.review_packet.verified_transport_fixture import (
    install_visual_authority,
)


def _install_scoped_case_run(
    root: Path,
    *,
    run_id: str,
    attachment_id: str,
    source_hash: str,
    image_bytes: bytes,
) -> str:
    image_sha256 = hashlib.sha256(image_bytes).hexdigest()
    page = root / "case-page-images-hq-v1" / attachment_id / "page-0001.png"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_bytes(image_bytes)
    model = {
        "case_visual_review": {
            "pages": [{
                "attachment_id": attachment_id,
                "document_name": f"{attachment_id}.png",
                "page": 1,
                "width": 1.0,
                "height": 1.0,
                "source_sha256": source_hash,
                "image_sha256": image_sha256,
                "tiles": [],
            }]
        }
    }
    install_visual_authority(
        root,
        model,
        run_id=run_id,
    )
    return image_sha256


def test_run_token_cannot_read_another_runs_verified_case_asset(tmp_path: Path) -> None:
    run_a = "RUN-AAAAAAAAAAAAAAAAAAAA"
    run_b = "RUN-BBBBBBBBBBBBBBBBBBBB"
    token_a = "d" * 43
    token_b = "e" * 43
    attachment_a = "ATT-A"
    attachment_b = "ATT-B"
    image_a = b"\x89PNG\r\n\x1a\nrun-a"
    image_b = b"\x89PNG\r\n\x1a\nrun-b"
    hash_a = _install_scoped_case_run(
        tmp_path,
        run_id=run_a,
        attachment_id=attachment_a,
        source_hash="1" * 64,
        image_bytes=image_a,
    )
    hash_b = _install_scoped_case_run(
        tmp_path,
        run_id=run_b,
        attachment_id=attachment_b,
        source_hash="2" * 64,
        image_bytes=image_b,
    )

    server = create_review_server(
        tmp_path,
        run_tokens={run_a: token_a, run_b: token_b},
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, delivered = _get(
            server,
            f"/runs/{run_a}/{token_a}/case-pages/{attachment_a}/1/{hash_a}",
        )
        assert status == 200
        assert delivered == image_a

        status, _, delivered = _get(
            server,
            f"/runs/{run_b}/{token_b}/case-pages/{attachment_b}/1/{hash_b}",
        )
        assert status == 200
        assert delivered == image_b

        status, _, body = _get(
            server,
            f"/runs/{run_a}/{token_a}/case-pages/{attachment_b}/1/{hash_b}",
        )
        assert status == 404
        assert image_b not in body

        status, _, body = _get(
            server,
            f"/runs/{run_b}/{token_b}/case-pages/{attachment_a}/1/{hash_a}",
        )
        assert status == 404
        assert image_a not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _reference_authorities(root: Path) -> dict[str, tuple[str, str, bytes]]:
    """Finalize one DB with two references, then bind each RUN to just its own citation."""
    database = root / "evidence" / "evidence.sqlite"
    with EvidenceStore(database, create=True) as store:
        connection = store.require_connection()
        for name in ("A", "B"):
            source_hash = ("1" if name == "A" else "2") * 64
            connection.execute("INSERT INTO documents(id,title) VALUES(?,?)",
                               (f"DOC-{name}", f"Reference {name}"))
            connection.execute(
                "INSERT INTO revisions(id,document_id,source_hash,byte_size,page_count) "
                "VALUES(?,?,?,10,1)", (f"REV-{name}", f"DOC-{name}", source_hash),
            )
            connection.execute(
                "INSERT INTO pages(id,revision_id,page_number,width,height) VALUES(?,?,1,100,100)",
                (f"PAGE-{name}", f"REV-{name}"),
            )
            connection.execute(
                "INSERT INTO elements(id,page_id,element_type,raw_json,raw_text,normalized_text,"
                "raw_payload_hash,bbox_json,parser_order) "
                "VALUES(?,?,'paragraph','{}','verified','verified',?,'[0,0,10,10]',0)",
                (f"E-{name}", f"PAGE-{name}", source_hash),
            )
            connection.execute(
                "INSERT INTO retrieval_records(evidence_id,evidence_type,document_id,revision_id,"
                "page_id,page_number,bbox_json,source_hash,title,raw_text,normalized_text) "
                "VALUES(?,'clause',?,?,?,1,'[0,0,10,10]',?,'Reference','verified','verified')",
                (f"E-{name}", f"DOC-{name}", f"REV-{name}", f"PAGE-{name}", source_hash),
            )
        for table in ("snapshot_meta", "retrieval_meta"):
            connection.execute(
                f"INSERT INTO {table}(key,value) VALUES('snapshot_hash',?)", ("a" * 64,),
            )
        connection.commit()
        finalize_evidence_database(store)
    provenance = finalized_evidence_provenance(database)
    result = {}
    for name in ("A", "B"):
        run_id = "RUN-" + name * 20
        source_hash = ("1" if name == "A" else "2") * 64
        staged = _write_run(root / f"fixture-{name}",
                            snapshot_hash=provenance["evidence_snapshot_hash"])
        target = root / "runs" / run_id
        target.mkdir(parents=True)
        manifest = json.loads((staged / "run-manifest.json").read_bytes())
        hashes = {}
        identities = {
            "RUN-0123456789ABCDEF0123": run_id,
            "DOC1": f"DOC-{name}", "REV1": f"REV-{name}",
            "E1": f"E-{name}", "C1": f"CIT-E-{name}", "a" * 64: source_hash,
        }
        for filename in manifest["artifacts"]:
            text = (staged / filename).read_text(encoding="utf-8")
            for old, new in identities.items():
                text = text.replace(json.dumps(old), json.dumps(new))
            document = json.loads(text)
            if filename == "track-a-bundle.json":
                document["inputs"]["evidence_snapshot_provenance"] = provenance
            data = dump_bytes(document)
            (target / filename).write_bytes(data)
            hashes[filename] = hashlib.sha256(data).hexdigest()
        (target / "run-manifest.json").write_bytes(
            dump_bytes({"run_id": run_id, "artifacts": hashes}),
        )
        finalize_run(target)
        (target / "review.html").write_text("protected entry", encoding="utf-8")
        output = BytesIO()
        Image.new("RGB", (2, 2), "red" if name == "A" else "blue").save(output, format="PNG")
        image_bytes = output.getvalue()
        directory = root / "page-images" / f"REV-{name}"
        directory.mkdir(parents=True)
        (directory / "page-0001.png").write_bytes(image_bytes)
        (directory / "page-0001.json").write_bytes(dump_bytes({
            "format": "evidence-review/page-image", "version": 1,
            "revision_id": f"REV-{name}", "page_number": 1, "source_hash": source_hash,
            "pdf_width": 100.0, "pdf_height": 100.0,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        }))
        result[name] = (run_id, source_hash, image_bytes)
    return result


def test_run_token_cannot_read_another_runs_verified_reference_asset(tmp_path: Path) -> None:
    references = _reference_authorities(tmp_path)
    tokens = {run_id: name.lower() * 43 for name, (run_id, _, _) in references.items()}
    server = create_review_server(tmp_path, run_tokens=tokens)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for name, (run_id, source_hash, image_bytes) in references.items():
            own = f"/runs/{run_id}/{tokens[run_id]}/page-images/REV-{name}/1/{source_hash}"
            status, _, delivered = _get(server, own)
            assert status == 200
            assert delivered == image_bytes
            other_name = "B" if name == "A" else "A"
            _, other_hash, other_bytes = references[other_name]
            cross = (
                f"/runs/{run_id}/{tokens[run_id]}/page-images/REV-{other_name}/1/{other_hash}"
            )
            status, _, denied = _get(server, cross)
            assert status == 404
            assert other_bytes not in denied
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
