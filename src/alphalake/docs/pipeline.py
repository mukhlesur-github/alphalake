"""Incremental document sync: only new/changed PDFs (by SHA-256) are re-parsed and re-published.

Output: data/landing/docs/parsed/<doc_id>__v<version>.json -> S3 -> Snowpipe -> BRONZE.DOC_PARSED_RAW.
The Snowflake task replaces all chunks of a doc_id when a newer version arrives (no stale vectors).
"""

import json
from datetime import UTC, datetime

from alphalake.common.config import get_settings
from alphalake.docs.parse import parse_document, sha256


def parse_all() -> None:
    s = get_settings()
    raw = s.data_dir / "docs" / "raw"
    out = s.data_dir / "landing" / "docs" / "parsed"
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = s.data_dir / "state" / "doc_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    changed = skipped = 0
    for pdf in sorted(raw.glob("*.pdf")):
        data = pdf.read_bytes()
        meta = json.loads(pdf.with_suffix(".meta.json").read_text())
        h = sha256(data)
        prev = manifest.get(meta["doc_id"])
        if prev and prev["sha256"] == h:
            skipped += 1
            continue
        version = (prev["version"] + 1) if prev else 1
        doc = parse_document(data, meta, version)
        doc["parsed_at"] = datetime.now(UTC).isoformat()
        doc["source_uri"] = f"s3://{s.alphalake_bucket}/landing/docs/raw/{pdf.name}"
        (out / f"{meta['doc_id']}__v{version}.json").write_text(json.dumps(doc))
        manifest[meta["doc_id"]] = {"sha256": h, "version": version}
        changed += 1
        print(f"parsed {meta['doc_id']} v{version}: {len(doc['chunks'])} chunks, {doc['pii_redactions']} PII redactions")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"{changed} changed, {skipped} unchanged (skipped)")
