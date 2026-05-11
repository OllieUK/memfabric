"""Shared PDF word-extraction utilities used by inspect_* and extract_cti_* scripts."""
from collections import defaultdict


def words_to_lines(words: list[dict], y_tolerance: float = 3.0) -> list[list[dict]]:
    """Group pdfplumber word dicts into visual lines by vertical midpoint."""
    buckets: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        mid_y = round((w["top"] + w["bottom"]) / 2 / y_tolerance) * y_tolerance
        buckets[mid_y].append(w)
    return [sorted(v, key=lambda w: w["x0"]) for _, v in sorted(buckets.items())]


def line_text(line_words: list[dict]) -> str:
    """Reconstruct line text from a list of pdfplumber word dicts."""
    return " ".join(w["text"] for w in line_words)
