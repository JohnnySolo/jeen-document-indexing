#!/usr/bin/env python3
"""Semantic search over indexed document chunks.

Examples
    python search.py --query "login issue"
    python search.py --query "login issue" --top-k 3
    python search.py --query "login issue" --strategy paragraph
    python search.py --query "login issue" --compare

--compare runs the same query separately against each chunking strategy and
prints the top result from each. This is what the split_strategy column is for:
indexing one document three ways and then looking at which strategy actually
retrieves the passage that answers the question.
"""

import argparse
import sys

import db
import embeddings
from config import STRATEGIES
from errors import ConfigurationError, DatabaseError, EmbeddingError

_PREVIEW_CHARS = 300


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search indexed documents by meaning rather than keyword.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--query", required=True, help="Natural language query.")
    parser.add_argument(
        "--top-k", type=int, default=5, help="Number of results to return."
    )
    parser.add_argument(
        "--strategy",
        choices=list(STRATEGIES),
        help="Restrict results to chunks produced by one strategy.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Show the best match from each chunking strategy side by side.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print whole chunks instead of a preview.",
    )
    return parser


def preview(text: str, full: bool) -> str:
    """Collapse a chunk to one readable line unless --full was requested."""
    collapsed = " ".join(text.split())
    if full or len(collapsed) <= _PREVIEW_CHARS:
        return collapsed
    return collapsed[:_PREVIEW_CHARS] + " ..."


def print_results(results, full: bool) -> None:
    for rank, row in enumerate(results, start=1):
        print(f"\n  [{rank}] similarity {row['similarity']:.4f}")
        print(
            f"      file: {row['filename']}  |  strategy: {row['split_strategy']}"
            f"  |  chunk #{row['chunk_index']}  |  id {row['id']}"
        )
        print(f"      {preview(row['chunk_text'], full)}")


def run_compare(connection, query_vector, top_k, full) -> bool:
    """Search each strategy separately. Returns True if anything was found."""
    found_any = False
    for strategy in STRATEGIES:
        results = db.search(connection, query_vector, top_k=top_k, strategy=strategy)
        print(f"\n--- strategy: {strategy} ---")
        if not results:
            print("  no chunks indexed under this strategy")
            continue
        found_any = True
        print_results(results, full)
    return found_any


def main() -> int:
    args = build_parser().parse_args()

    try:
        print(f'Query: "{args.query}"')
        query_vector = embeddings.embed_query(args.query)

        with db.connect() as connection:
            if args.compare:
                found = run_compare(connection, query_vector, args.top_k, args.full)
            else:
                results = db.search(
                    connection,
                    query_vector,
                    top_k=args.top_k,
                    strategy=args.strategy,
                )
                found = bool(results)
                if found:
                    label = f" (strategy: {args.strategy})" if args.strategy else ""
                    print(f"\n{len(results)} result(s){label}")
                    print_results(results, args.full)

            if not found:
                print(
                    "\nNo results found. The table may be empty, or no chunk was "
                    "indexed under the requested strategy. Index a document first:"
                    "\n  python index_documents.py --file ./docs/example.pdf "
                    "--strategy all"
                )
                return 0

        print()
        return 0

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
