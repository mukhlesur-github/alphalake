import json

from alphalake.docs.parse import redact


def test_prospectus_limits_table_survives_as_markdown(generated):
    doc = json.loads((generated / "landing/docs/parsed/PROSP-GTIF__v1.json").read_text())
    tables = [c for c in doc["chunks"] if c["chunk_type"] == "table"]
    limits = [t for t in tables if t["section_title"] == "Investment Restrictions"]
    assert limits and "|Semiconductors sub-industry|35% of net assets|" in limits[0]["chunk_text"]
    assert doc["sha256"] and doc["version"] == 1


def test_pii_redaction():
    text, n = redact("mail jane.doe@x.com or call (415) 555-0142, SSN 123-45-6789")
    assert n == 3 and "@" not in text and "6789" not in text


def test_unchanged_docs_are_skipped_and_changed_docs_bump_version(generated, capsys):
    from alphalake.docs.pipeline import parse_all
    from alphalake.generators.documents import write_pdf
    parse_all()
    assert "0 changed" in capsys.readouterr().out
    write_pdf(generated / "docs/raw/POLICY-BESTEX.pdf", "<h1>Best Execution Policy</h1><p>Revised 2026.</p>")
    parse_all()
    assert "1 changed" in capsys.readouterr().out
    assert (generated / "landing/docs/parsed/POLICY-BESTEX__v2.json").exists()
