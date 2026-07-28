#!/usr/bin/env python3
"""Index a PDF or DOCX file into PostgreSQL with pgvector.

Examples
    python index_documents.py --file ./docs/example.pdf --strategy paragraph
    python index_documents.py --file ./docs/example.docx --strategy all
    python index_documents.py --file ./docs/example.pdf --strategy fixed \
        --chunk-size 800 --overlap 100

Every failure the assignment lists is caught and reported as a single readable
line with a non-zero exit code, never as a stack trace.
"""

import argparse
import sys
from pathlib import Path

import chunking
import db
import embeddings
import extraction
from config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_SENTENCES_PER_CHUNK,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    STRATEGIES,
)
from errors import (
    ConfigurationError,
    DatabaseError,
    EmbeddingError,
    ExtractionError,
    NoExtractableTextError,
    UnsupportedFileTypeError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract, chunk, embed and store a document for semantic search.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to a .pdf or .docx file.",
    )
    parser.add_argument(
        "--strategy",
        default="paragraph",
        choices=list(STRATEGIES) + ["all"],
        help="Chunking strategy. 'all' indexes the document three times, once "
             "per strategy, so retrieval quality can be compared.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Characters per chunk. Used by the 'fixed' strategy only.",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help="Overlapping characters between chunks. 'fixed' strategy only.",
    )
    parser.add_argument(
        "--sentences-per-chunk",
        type=int,
        default=DEFAULT_SENTENCES_PER_CHUNK,
        help="Sentences per chunk. Used by the 'sentence' strategy only.",
    )
    return parser


def index_one_strategy(connection, filename, text, strategy, options) -> int:
    """Chunk, embed and store the document under a single strategy."""
    print(f"\n  Strategy: {strategy}")

    chunks = chunking.chunk_text(strategy, text, **options)
    if not chunks:
        print("    No chunks produced. Skipping.")
        return 0
    print(f"    {len(chunks)} chunks produced")

    vectors = embeddings.embed_documents(chunks)

    removed = db.delete_existing(connection, filename, strategy)
    if removed:
        print(f"    removed {removed} previously indexed chunks")

    inserted = db.insert_chunks(connection, filename, strategy, chunks, vectors)
    print(f"    stored {inserted} chunks")
    return inserted


def main() -> int:
    args = build_parser().parse_args()

    try:
        print(f"Reading: {args.file}")
        text = extraction.extract_text(args.file)
        filename = Path(args.file).name
        print(f"  extracted {len(text):,} characters")

        strategies = list(STRATEGIES) if args.strategy == "all" else [args.strategy]
        options = {
            "chunk_size": args.chunk_size,
            "overlap": args.overlap,
            "sentences_per_chunk": args.sentences_per_chunk,
        }

        print(f"\nEmbedding model: {EMBEDDING_MODEL} at {EMBEDDING_DIM} dimensions")

        with db.connect() as connection:
            db.ensure_schema(connection)

            total = 0
            for strategy in strategies:
                total += index_one_strategy(
                    connection, filename, text, strategy, options
                )

            print(f"\nDone. {total} chunks indexed from {filename}.")

            summary = db.table_summary(connection)
            if summary:
                print("\nCurrent contents of the table:")
                for row in summary:
                    print(
                        f"  {row['filename']:<40} "
                        f"{row['split_strategy']:<10} "
                        f"{row['chunk_count']:>5} chunks"
                    )
        return 0

    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except UnsupportedFileTypeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except NoExtractableTextError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except ExtractionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except EmbeddingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except DatabaseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
