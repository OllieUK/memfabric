"""Chunking utilities for ingest_document.py.

chunk_markdown: split a Markdown string into sections by ## / ### headings.
chunk_pdf: extract text from a PDF file and split into overlapping windows.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkData:
    text: str
    sequence: int
    heading: str = ""  # metadata; heading is also prepended into text


def chunk_markdown(text: str, min_chars: int = 50) -> list[ChunkData]:
    """Split Markdown text into chunks by ## / ### headings.

    Each chunk's text is: "<heading>\\n<body>" (heading prepended so the
    embedding captures section context).

    Documents with no ## / ### headings are treated as a single chunk if
    they meet min_chars.
    """
    chunks: list[ChunkData] = []
    current_heading = ""
    current_body: list[str] = []

    def _flush(heading: str, body_lines: list[str]) -> None:
        body = "\n".join(body_lines).strip()
        candidate = (heading + "\n" + body).strip() if heading else body
        if len(candidate) >= min_chars:
            chunks.append(ChunkData(text=candidate, sequence=0, heading=heading))

    for line in text.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            if current_body or current_heading:
                _flush(current_heading, current_body)
            current_heading = line.lstrip("# ").strip()
            current_body = []
        else:
            current_body.append(line)

    # flush the final section
    _flush(current_heading, current_body)

    # Re-sequence to be contiguous 0-based
    for i, c in enumerate(chunks):
        c.sequence = i

    return chunks


def chunk_pdf(
    path: str,
    chunk_size: int = 2000,
    overlap: int = 200,
    min_chars: int = 50,
) -> list[ChunkData]:
    """Extract text from a PDF file and split into overlapping windows.

    Each window is chunk_size characters; adjacent windows overlap by
    overlap characters to avoid cutting evidence at boundaries.

    Raises ValueError if overlap >= chunk_size (would cause infinite loop).
    """
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        )
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is required for PDF ingestion. "
            "Install with: pip install pdfplumber"
        ) from exc

    full_text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            full_text += page_text + "\n"

    chunks: list[ChunkData] = []
    start = 0
    seq = 0
    while start < len(full_text):
        end = start + chunk_size
        candidate = full_text[start:end].strip()
        if len(candidate) >= min_chars:
            chunks.append(ChunkData(text=candidate, sequence=seq, heading=""))
            seq += 1
        start += chunk_size - overlap

    return chunks
