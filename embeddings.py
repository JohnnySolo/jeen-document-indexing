"""Embedding generation via the Gemini API.

Three details here are easy to get wrong and produce no error when wrong:

  1. Dimensionality. The model returns 3072 dimensions by default, which
     exceeds pgvector's 2000-dimension index limit. A reduced output is
     requested explicitly.

  2. Normalisation. The model's full-length output is unit length, but a
     truncated output is not. Re-normalising is required for cosine similarity
     scores to be comparable. Skipping it silently distorts every ranking.

  3. Request pacing. The free tier allows a limited number of embedding calls
     per minute. Reacting to a 429 after the fact is not enough, because the
     server-requested wait can exceed a naive backoff by an order of magnitude.
     A sliding-window limiter keeps the client below the ceiling, and 429
     responses are additionally honoured by reading the server's own retry
     delay rather than guessing.

Task type also matters: documents and queries are embedded with different task
types so that the model places a question near the passage that answers it,
rather than near other questions.
"""

import math
import re
import time
from collections import deque
from typing import List, Optional

from google import genai
from google.genai import types

from config import EMBEDDING_DIM, EMBEDDING_MODEL, get_api_key
from errors import EmbeddingError

# The documented free-tier ceiling is 100 embedding requests per minute. The
# client stays below it deliberately, leaving headroom for clock skew and for
# any request the server counts that the client does not.
_REQUESTS_PER_MINUTE = 85
_WINDOW_SECONDS = 60.0

_MAX_ATTEMPTS = 5
_DEFAULT_BACKOFF_SECONDS = 5.0
_MAX_SLEEP_SECONDS = 120.0

_client = None
_request_times: deque = deque()


def _get_client():
    """Create the Gemini client once and reuse it."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_api_key())
    return _client


def normalize(vector: List[float]) -> List[float]:
    """Scale a vector to unit length. Required after dimensionality reduction."""
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0.0:
        return vector
    return [value / magnitude for value in vector]


def _prune_window(now: float) -> None:
    """Drop request timestamps that have fallen outside the sliding window."""
    while _request_times and now - _request_times[0] > _WINDOW_SECONDS:
        _request_times.popleft()


def _throttle(verbose: bool = True) -> None:
    """Block until another request can be made without exceeding the ceiling."""
    now = time.monotonic()
    _prune_window(now)

    if len(_request_times) >= _REQUESTS_PER_MINUTE:
        wait = _WINDOW_SECONDS - (now - _request_times[0]) + 0.5
        if wait > 0:
            if verbose:
                print(
                    f"\n    rate limit guard: pausing {wait:.0f}s "
                    f"to stay under {_REQUESTS_PER_MINUTE} requests/min"
                )
            time.sleep(wait)
        _prune_window(time.monotonic())

    _request_times.append(time.monotonic())


def _server_retry_delay(exc: Exception) -> Optional[float]:
    """Read the retry delay the server asked for, if it supplied one."""
    text = str(exc)
    for pattern in (r"retry in ([\d.]+)s", r"'retryDelay': '([\d.]+)s'"):
        match = re.search(pattern, text)
        if match:
            return min(float(match.group(1)) + 2.0, _MAX_SLEEP_SECONDS)
    return None


def _is_rate_limit(exc: Exception) -> bool:
    """Identify a quota or rate-limit rejection."""
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def _embed_once(text: str, task_type: str) -> List[float]:
    """Single embedding call. Raises on any API failure."""
    client = _get_client()
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=EMBEDDING_DIM,
            task_type=task_type,
        ),
    )
    values = list(response.embeddings[0].values)
    if len(values) != EMBEDDING_DIM:
        raise EmbeddingError(
            f"Expected {EMBEDDING_DIM} dimensions, received {len(values)}."
        )
    return normalize(values)


def embed_text(
    text: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
    verbose: bool = True,
) -> List[float]:
    """Embed one string, pacing requests and honouring server retry delays."""
    last_error = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        _throttle(verbose=verbose)
        try:
            return _embed_once(text, task_type)
        except Exception as exc:
            last_error = exc
            if attempt == _MAX_ATTEMPTS:
                break

            if _is_rate_limit(exc):
                wait = _server_retry_delay(exc) or _WINDOW_SECONDS
                if verbose:
                    print(
                        f"\n    rate limited by the server, waiting {wait:.0f}s "
                        f"(attempt {attempt}/{_MAX_ATTEMPTS})"
                    )
                # The window is stale after a server-side rejection.
                _request_times.clear()
            else:
                wait = _DEFAULT_BACKOFF_SECONDS * attempt
                if verbose:
                    print(
                        f"\n    transient error, retrying in {wait:.0f}s "
                        f"(attempt {attempt}/{_MAX_ATTEMPTS})"
                    )
            time.sleep(wait)

    raise EmbeddingError(
        f"Embedding failed after {_MAX_ATTEMPTS} attempts: "
        f"{type(last_error).__name__}: {last_error}"
    )


def embed_documents(texts: List[str], progress: bool = True) -> List[List[float]]:
    """Embed a list of document chunks, reporting progress as it goes."""
    vectors = []
    total = len(texts)
    for index, text in enumerate(texts, start=1):
        vectors.append(embed_text(text, task_type="RETRIEVAL_DOCUMENT"))
        if progress:
            print(f"    embedded {index}/{total}", end="\r", flush=True)
    if progress and total:
        print(f"    embedded {total}/{total}")
    return vectors


def embed_query(text: str) -> List[float]:
    """Embed a search query using the query task type."""
    return embed_text(text, task_type="RETRIEVAL_QUERY", verbose=False)
