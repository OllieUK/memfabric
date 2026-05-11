"""Unit tests for chunk_markdown and chunk_pdf (no live stack, no Memgraph)."""
import builtins
import os
import tempfile

import pytest

from cyber_knowledge.ingest.chunkers import ChunkData, chunk_markdown, chunk_pdf


# --- chunk_markdown ---

def test_chunk_markdown_single_heading_section():
    """## heading + body → one chunk with heading prepended."""
    text = "## Introduction\nThis is the body text for the intro section."
    chunks = chunk_markdown(text, min_chars=10)
    assert len(chunks) == 1
    assert chunks[0].heading == "Introduction"
    assert "Introduction" in chunks[0].text
    assert "body text" in chunks[0].text
    assert chunks[0].sequence == 0


def test_chunk_markdown_no_headings_single_chunk():
    """Headingless text treated as single chunk if above min_chars."""
    text = "No headings here. Just plain text that is long enough."
    chunks = chunk_markdown(text, min_chars=10)
    assert len(chunks) == 1
    assert chunks[0].text.strip() != ""
    assert chunks[0].heading == ""


def test_chunk_markdown_short_sections_skipped():
    """Sections below min_chars are dropped."""
    text = "## Short\nHi\n## Long section\n" + ("a" * 100)
    chunks = chunk_markdown(text, min_chars=50)
    # "Short\nHi" is < 50 chars; long section is >= 50
    assert len(chunks) == 1
    assert "Long section" in chunks[0].text


def test_chunk_markdown_multi_heading():
    """Three ## sections → three chunks in order."""
    text = (
        "## Section One\n" + ("a" * 60) + "\n"
        "## Section Two\n" + ("b" * 60) + "\n"
        "## Section Three\n" + ("c" * 60)
    )
    chunks = chunk_markdown(text, min_chars=10)
    assert len(chunks) == 3
    assert chunks[0].heading == "Section One"
    assert chunks[1].heading == "Section Two"
    assert chunks[2].heading == "Section Three"
    # Sequences must be contiguous 0-based
    assert [c.sequence for c in chunks] == [0, 1, 2]


def test_chunk_markdown_h3_treated_same_as_h2():
    """### headings also trigger section boundaries."""
    text = "### Sub A\n" + ("x" * 60) + "\n### Sub B\n" + ("y" * 60)
    chunks = chunk_markdown(text, min_chars=10)
    assert len(chunks) == 2
    assert chunks[0].heading == "Sub A"
    assert chunks[1].heading == "Sub B"


def test_chunk_markdown_heading_prepended_in_text():
    """The chunk text starts with the heading followed by newline then body."""
    text = "## My Heading\nSome content here that is long enough."
    chunks = chunk_markdown(text, min_chars=10)
    assert len(chunks) == 1
    assert chunks[0].text.startswith("My Heading\n")


def test_chunk_markdown_empty_string():
    """Empty input returns no chunks."""
    chunks = chunk_markdown("", min_chars=10)
    assert chunks == []


def test_chunk_markdown_only_heading_no_body():
    """A heading with no body that is below min_chars is skipped."""
    text = "## Title"
    chunks = chunk_markdown(text, min_chars=50)
    assert len(chunks) == 0


def test_chunk_markdown_sequences_are_contiguous():
    """Sequences are always contiguous 0-based even when sections are skipped."""
    text = (
        "## Short\nHi\n"          # skipped (< 50)
        "## Long One\n" + ("x" * 60) + "\n"
        "## Also Short\nBye\n"    # skipped (< 50)
        "## Long Two\n" + ("y" * 60)
    )
    chunks = chunk_markdown(text, min_chars=50)
    assert len(chunks) == 2
    assert [c.sequence for c in chunks] == [0, 1]


# --- chunk_pdf ---

def test_chunk_pdf_character_window():
    """chunk_pdf creates overlapping windows from PDF text."""
    pytest.importorskip("pdfplumber")
    pytest.importorskip("fpdf")

    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    long_text = "ABCDEF " * 400  # ~2800 chars
    pdf.multi_cell(0, 10, long_text)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp_path = f.name
        pdf.output(tmp_path)

    try:
        chunks = chunk_pdf(tmp_path, chunk_size=1000, overlap=100, min_chars=50)
        assert len(chunks) >= 2
        # sequences are contiguous 0-based
        assert [c.sequence for c in chunks] == list(range(len(chunks)))
        # all chunks meet min_chars
        for c in chunks:
            assert len(c.text) >= 50
    finally:
        os.unlink(tmp_path)


def test_chunk_pdf_min_chars_filter():
    """Chunks below min_chars are skipped."""
    pytest.importorskip("pdfplumber")
    pytest.importorskip("fpdf")

    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Short")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp_path = f.name
        pdf.output(tmp_path)

    try:
        chunks = chunk_pdf(tmp_path, chunk_size=2000, overlap=200, min_chars=50)
        for c in chunks:
            assert len(c.text) >= 50
    finally:
        os.unlink(tmp_path)


def test_chunk_pdf_import_error_without_pdfplumber(monkeypatch):
    """chunk_pdf raises ImportError with helpful message when pdfplumber missing."""
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "pdfplumber":
            raise ImportError("No module named 'pdfplumber'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    with pytest.raises(ImportError, match="pdfplumber"):
        chunk_pdf("any.pdf")


def test_chunk_pdf_heading_is_empty():
    """PDF chunks always have empty heading string."""
    pytest.importorskip("pdfplumber")
    pytest.importorskip("fpdf")

    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, "Hello world " * 100)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp_path = f.name
        pdf.output(tmp_path)

    try:
        chunks = chunk_pdf(tmp_path, chunk_size=500, overlap=50, min_chars=10)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.heading == ""
    finally:
        os.unlink(tmp_path)
