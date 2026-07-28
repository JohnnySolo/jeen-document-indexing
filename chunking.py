"""Three chunking strategies.

Each function takes plain text and returns a list of non-empty chunk strings.
The strategy used for a chunk is stored alongside it in the database, so the
same document can be indexed under all three and the retrieval quality of each
compared directly.

  fixed      Cut every N characters with an overlap. Predictable chunk sizes,
             ignores meaning, and will cut mid-sentence. The overlap exists so
             that an idea straddling a boundary still appears whole somewhere.

  sentence   Group N consecutive sentences. Chunks end on sentence boundaries
             but vary in length, so one chunk may hold far more content
             than another.

  paragraph  One chunk per paragraph, using the author's own structure. Usually
             the most semantically coherent, but entirely dependent on the
             source document actually having paragraph breaks.
"""

import re
from typing import List

from config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_SENTENCES_PER_CHUNK,
)

# Split after . ! ? or the Hebrew maqaf-free sentence enders, when followed by
# whitespace. Deliberately simple: no abbreviation dictionary, because a wrong
# abbreviation list is worse than a predictable rule.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")


def chunk_fixed(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split into fixed-size character windows that overlap by `overlap`."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap cannot be negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks = []
    step = chunk_size - overlap
    for start in range(0, len(text), step):
        window = text[start : start + chunk_size].strip()
        if window:
            chunks.append(window)
        if start + chunk_size >= len(text):
            break
    return chunks


def chunk_sentences(
    text: str,
    sentences_per_chunk: int = DEFAULT_SENTENCES_PER_CHUNK,
) -> List[str]:
    """Group consecutive sentences into chunks of `sentences_per_chunk`."""
    if sentences_per_chunk <= 0:
        raise ValueError("sentences_per_chunk must be positive")

    flattened = " ".join(line for line in text.split("\n") if line.strip())
    sentences = [s.strip() for s in _SENTENCE_BOUNDARY.split(flattened) if s.strip()]

    chunks = []
    for start in range(0, len(sentences), sentences_per_chunk):
        group = sentences[start : start + sentences_per_chunk]
        joined = " ".join(group).strip()
        if joined:
            chunks.append(joined)
    return chunks


def chunk_paragraphs(text: str) -> List[str]:
    """One chunk per paragraph, as delimited by blank lines."""
    paragraphs = [p.strip() for p in _PARAGRAPH_BOUNDARY.split(text)]
    return [p for p in paragraphs if p]


def chunk_text(strategy: str, text: str, **options) -> List[str]:
    """Dispatch to the requested strategy.

    Recognised options: chunk_size, overlap (fixed); sentences_per_chunk
    (sentence). Unrecognised options for a strategy are ignored.
    """
    if strategy == "fixed":
        return chunk_fixed(
            text,
            chunk_size=options.get("chunk_size", DEFAULT_CHUNK_SIZE),
            overlap=options.get("overlap", DEFAULT_CHUNK_OVERLAP),
        )
    if strategy == "sentence":
        return chunk_sentences(
            text,
            sentences_per_chunk=options.get(
                "sentences_per_chunk", DEFAULT_SENTENCES_PER_CHUNK
            ),
        )
    if strategy == "paragraph":
        return chunk_paragraphs(text)

    raise ValueError(f"Unknown chunking strategy: {strategy}")
