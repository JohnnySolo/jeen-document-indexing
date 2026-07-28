"""PostgreSQL and pgvector access layer.

Vectors are passed as pgvector's text literal form and cast in SQL. This avoids
an extra adapter dependency and keeps the wire format explicit.

Cosine distance (the <=> operator) is used for search. Similarity is reported as
1 - distance, so higher is better and the range is easy to read.
"""

from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg

from config import EMBEDDING_DIM, TABLE_NAME, get_postgres_url
from errors import DatabaseError


def to_vector_literal(vector: List[float]) -> str:
    """Render a Python list as a pgvector literal, e.g. '[0.1,0.2]'."""
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


@contextmanager
def connect():
    """Yield a database connection, converting driver errors into DatabaseError."""
    try:
        connection = psycopg.connect(get_postgres_url())
    except psycopg.OperationalError as exc:
        raise DatabaseError(
            "Could not connect to PostgreSQL. Check POSTGRES_URL in .env, and "
            "that the database is reachable.\n"
            f"Driver message: {exc}"
        ) from exc
    except Exception as exc:
        raise DatabaseError(f"Unexpected database error: {exc}") from exc

    try:
        yield connection
    finally:
        connection.close()


def ensure_schema(connection) -> None:
    """Create the extension, table and index if they do not already exist."""
    create_table = f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id             SERIAL PRIMARY KEY,
            chunk_text     TEXT        NOT NULL,
            embedding      vector({EMBEDDING_DIM}) NOT NULL,
            filename       TEXT        NOT NULL,
            split_strategy TEXT        NOT NULL,
            chunk_index    INTEGER     NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """
    create_index = f"""
        CREATE INDEX IF NOT EXISTS {TABLE_NAME}_embedding_idx
        ON {TABLE_NAME} USING hnsw (embedding vector_cosine_ops);
    """
    create_lookup_index = f"""
        CREATE INDEX IF NOT EXISTS {TABLE_NAME}_file_strategy_idx
        ON {TABLE_NAME} (filename, split_strategy);
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cursor.execute(create_table)
            cursor.execute(create_index)
            cursor.execute(create_lookup_index)
        connection.commit()
    except Exception as exc:
        connection.rollback()
        raise DatabaseError(f"Could not create the schema: {exc}") from exc


def delete_existing(connection, filename: str, strategy: str) -> int:
    """Remove prior rows for this file and strategy so re-indexing is idempotent."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {TABLE_NAME} "
                "WHERE filename = %s AND split_strategy = %s;",
                (filename, strategy),
            )
            removed = cursor.rowcount
        connection.commit()
        return removed
    except Exception as exc:
        connection.rollback()
        raise DatabaseError(f"Could not clear previous rows: {exc}") from exc


def insert_chunks(
    connection,
    filename: str,
    strategy: str,
    chunks: List[str],
    vectors: List[List[float]],
) -> int:
    """Insert chunks and their embeddings in a single transaction."""
    if len(chunks) != len(vectors):
        raise DatabaseError(
            f"Chunk count ({len(chunks)}) does not match vector count ({len(vectors)})."
        )

    statement = f"""
        INSERT INTO {TABLE_NAME}
            (chunk_text, embedding, filename, split_strategy, chunk_index)
        VALUES (%s, %s::vector, %s, %s, %s);
    """
    rows = [
        (text, to_vector_literal(vector), filename, strategy, index)
        for index, (text, vector) in enumerate(zip(chunks, vectors))
    ]

    try:
        with connection.cursor() as cursor:
            cursor.executemany(statement, rows)
        connection.commit()
        return len(rows)
    except Exception as exc:
        connection.rollback()
        raise DatabaseError(f"Could not insert chunks: {exc}") from exc


def search(
    connection,
    query_vector: List[float],
    top_k: int = 5,
    strategy: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return the nearest chunks by cosine distance, optionally filtered."""
    literal = to_vector_literal(query_vector)

    if strategy:
        statement = f"""
            SELECT id, chunk_text, filename, split_strategy, chunk_index,
                   created_at, 1 - (embedding <=> %s::vector) AS similarity
            FROM {TABLE_NAME}
            WHERE split_strategy = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """
        params = (literal, strategy, literal, top_k)
    else:
        statement = f"""
            SELECT id, chunk_text, filename, split_strategy, chunk_index,
                   created_at, 1 - (embedding <=> %s::vector) AS similarity
            FROM {TABLE_NAME}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """
        params = (literal, literal, top_k)

    try:
        with connection.cursor() as cursor:
            cursor.execute(statement, params)
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except psycopg.errors.UndefinedTable as exc:
        raise DatabaseError(
            f"Table '{TABLE_NAME}' does not exist. Index a document first with "
            "index_documents.py."
        ) from exc
    except Exception as exc:
        raise DatabaseError(f"Search query failed: {exc}") from exc


def table_summary(connection) -> List[Dict[str, Any]]:
    """Return row counts grouped by file and strategy, for the CLI footer."""
    statement = f"""
        SELECT filename, split_strategy, COUNT(*) AS chunk_count
        FROM {TABLE_NAME}
        GROUP BY filename, split_strategy
        ORDER BY filename, split_strategy;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(statement)
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except psycopg.errors.UndefinedTable:
        return []
    except Exception as exc:
        raise DatabaseError(f"Could not read table summary: {exc}") from exc
