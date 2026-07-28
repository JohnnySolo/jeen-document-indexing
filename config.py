"""Configuration loaded from environment variables.

All secrets are read from a .env file that is never committed. No credential
appears in source code, and no credential is ever printed.
"""

import os

from dotenv import load_dotenv

from errors import ConfigurationError

load_dotenv()

# gemini-embedding-001 returns 3072 dimensions by default. pgvector's HNSW and
# IVFFlat indexes support at most 2000 dimensions, so a reduced output is
# requested. The model is trained with Matryoshka representation learning, so a
# truncated vector remains meaningful, but it loses unit length and must be
# re-normalised before storage (see embeddings.normalize).
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 1536

TABLE_NAME = "document_chunks"

# Chunking defaults. Overridable per run from the command line.
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150
DEFAULT_SENTENCES_PER_CHUNK = 5

SUPPORTED_EXTENSIONS = (".pdf", ".docx")

STRATEGIES = ("fixed", "sentence", "paragraph")


def get_api_key() -> str:
    """Return the Gemini API key, or raise a clear configuration error."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ConfigurationError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return key


def get_postgres_url() -> str:
    """Return the PostgreSQL connection URL, or raise a clear configuration error."""
    url = os.environ.get("POSTGRES_URL")
    if not url:
        raise ConfigurationError(
            "POSTGRES_URL is not set. Copy .env.example to .env and fill it in."
        )
    return url
