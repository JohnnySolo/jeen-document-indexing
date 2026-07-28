"""Exception types for this module.

Each maps to one of the failure cases the CLI must handle gracefully, so that
callers can print a readable message instead of a stack trace.
"""


class IndexerError(Exception):
    """Base class for every error this package raises deliberately."""


class ConfigurationError(IndexerError):
    """A required environment variable is missing or empty."""


class UnsupportedFileTypeError(IndexerError):
    """The file extension is not one this module can read."""


class NoExtractableTextError(IndexerError):
    """The file was read successfully but contained no usable text."""


class ExtractionError(IndexerError):
    """The file exists and has a supported type but could not be parsed."""


class EmbeddingError(IndexerError):
    """The embedding API call failed after all retries."""


class DatabaseError(IndexerError):
    """The database could not be reached or a statement failed."""
