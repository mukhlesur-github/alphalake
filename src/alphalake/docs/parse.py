"""Layout-aware PDF parsing: headings by font size, tables -> markdown, section-aware chunks."""

import hashlib
import re
from dataclasses import asdict, dataclass

import pymupdf

HEADING_MIN_SIZE = 12.5
CHUNK_CHARS = 1200

PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\(?\b\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"), "[PHONE]"),
]


@dataclass
class Chunk:
    chunk_index: int
    chunk_type: str  # text | table
    section_title: str
    page_number: int
    chunk_text: str


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(text: str) -> tuple[str, int]:
    n = 0
    for pat, repl in PII_PATTERNS:
        text, k = pat.subn(repl, text)
        n += k
    return text, n


def _inside(bbox, rects) -> bool:
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return any(r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1 for r in rects)


def page_elements(page: pymupdf.Page) -> list[tuple[float, str, str]]:
    """(y, kind, text) in reading order; kind in heading|text|table."""
    tables = page.find_tables().tables
    rects = [pymupdf.Rect(t.bbox) for t in tables]
    out = [(t.bbox[1], "table", t.to_markdown().strip()) for t in tables]
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0 or _inside(block["bbox"], rects):
            continue
        spans = [s for line in block["lines"] for s in line["spans"] if s["text"].strip()]
        if not spans:
            continue
        text = " ".join(" ".join(s["text"] for s in line["spans"]).strip() for line in block["lines"]).strip()
        kind = "heading" if max(s["size"] for s in spans) >= HEADING_MIN_SIZE else "text"
        out.append((block["bbox"][1], kind, text))
    return sorted(out, key=lambda e: e[0])


def chunk_pdf(data: bytes) -> list[Chunk]:
    """Text accumulates per section up to CHUNK_CHARS; tables are always their own chunk and carry
    their section title, so 'Investment Restrictions' + the limits table stay retrievable together."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    chunks: list[Chunk] = []
    section, buf, buf_page = "", [], 1

    def flush():
        nonlocal buf
        if buf:
            chunks.append(Chunk(len(chunks), "text", section, buf_page, " ".join(buf)))
            buf = []

    for page in doc:
        for _, kind, text in page_elements(page):
            if kind == "heading":
                flush()
                section = text
            elif kind == "table":
                flush()
                chunks.append(Chunk(len(chunks), "table", section, page.number + 1, f"{section}\n\n{text}"))
            else:
                if not buf:
                    buf_page = page.number + 1
                if sum(map(len, buf)) + len(text) > CHUNK_CHARS:
                    flush()
                    buf_page = page.number + 1
                buf.append(text)
    flush()
    return chunks


def parse_document(data: bytes, meta: dict, version: int) -> dict:
    chunks, pii = [], 0
    for c in chunk_pdf(data):
        c.chunk_text, n = redact(c.chunk_text)
        pii += n
        chunks.append(asdict(c))
    return {**meta, "version": version, "sha256": sha256(data), "pii_redactions": pii, "chunks": chunks}
