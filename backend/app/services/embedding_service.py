"""Local FastEmbed inference for the workspace document vectors."""

import logging
import math
import os
import time

from app.schemas.documents import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

MODEL_ID = "BAAI/bge-small-en-v1.5"
_MODEL = None
_MODEL_ERROR: Exception | None = None
_LAST_FAILURE_AT = 0.0
_RETRY_AFTER_SECONDS = 60.0


class EmbeddingModelUnavailableError(RuntimeError):
    """Raised when the local model cannot be loaded for an indexing attempt."""


def initialize_embedding_model(*, force: bool = False) -> bool:
    """Load the ONNX model once; return False when it is unavailable."""
    global _MODEL, _MODEL_ERROR, _LAST_FAILURE_AT

    if _MODEL is not None:
        return True
    if (
        _MODEL_ERROR is not None
        and not force
        and time.monotonic() - _LAST_FAILURE_AT < _RETRY_AFTER_SECONDS
    ):
        return False

    try:
        from fastembed import TextEmbedding

        cache_dir = os.getenv("FASTEMBED_CACHE_PATH") or None
        _MODEL = TextEmbedding(model_name=MODEL_ID, cache_dir=cache_dir)
        _MODEL_ERROR = None
        logger.info(
            "Loaded local FastEmbed model=%s dimensions=%d cache=%s",
            MODEL_ID,
            EMBEDDING_DIMENSIONS,
            cache_dir or "FastEmbed default",
        )
        return True
    except Exception as exc:
        _MODEL = None
        _MODEL_ERROR = exc
        _LAST_FAILURE_AT = time.monotonic()
        logger.exception(
            "Could not initialize local FastEmbed model=%s cache=%s; check outbound DNS/network and model cache",
            MODEL_ID,
            os.getenv("FASTEMBED_CACHE_PATH") or "FastEmbed default",
        )
        return False


def _get_model():
    if not initialize_embedding_model():
        reason = (
            f"{type(_MODEL_ERROR).__name__}: {_MODEL_ERROR}"
            if _MODEL_ERROR
            else "model initialization did not complete"
        )
        raise EmbeddingModelUnavailableError(
            f"Local embedding model {MODEL_ID} is unavailable ({reason}). "
            "Check the service's DNS/network access to Hugging Face or its model cache, then retry indexing."
        ) from _MODEL_ERROR
    return _MODEL


def _normalize(vector) -> list[float]:
    values = [float(value) for value in vector]
    if len(values) != EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            f"Embedding model returned {len(values)} dimensions; expected {EMBEDDING_DIMENSIONS}"
        )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("Embedding model returned a non-finite value")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise RuntimeError("Embedding model returned a zero vector")
    return [value / norm for value in values]


def generate_embedding(text: str) -> list[float]:
    """Convert one non-empty string into a normalized 384-dimensional vector."""
    if not text.strip():
        raise ValueError("Cannot generate an embedding for empty text")
    return generate_embeddings([text])[0]


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate normalized vectors locally through the cached ONNX model."""
    if not texts:
        return []
    if any(not text.strip() for text in texts):
        raise ValueError("Cannot embed empty text")

    vectors = list(_get_model().embed(texts))
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"Embedding count mismatch: expected {len(texts)}, received {len(vectors)}"
        )
    return [_normalize(vector) for vector in vectors]
