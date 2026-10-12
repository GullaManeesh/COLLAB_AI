
import math
import os
import logging

import httpx

logger = logging.getLogger(__name__)

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
HF_API_URL = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{MODEL_ID}"

# Optional — works without a token for public models, but rate limits are higher with one
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")

# Maximum texts per request (HF Inference API limit)
_BATCH_SIZE = 128

# Retry settings for cold-start / model loading delays
_MAX_RETRIES = 3
_RETRY_DELAY = 5.0  # seconds


def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if HF_API_TOKEN:
        headers["Authorization"] = f"Bearer {HF_API_TOKEN}"
    return headers


def _normalize(vector: list[float]) -> list[float]:
    """L2-normalize a vector so cosine similarity = dot product."""
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def _call_hf_api(payload: dict) -> list:
    """
    Call the HuggingFace Inference API with retry logic for model cold starts.
    """
    import time

    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    HF_API_URL,
                    json=payload,
                    headers=_headers(),
                )

            if response.status_code == 503:
                # Model is loading — wait and retry
                body = response.json()
                wait = body.get("estimated_time", _RETRY_DELAY)
                logger.info(
                    "HF model loading (attempt %d/%d), waiting %.1fs…",
                    attempt, _MAX_RETRIES, wait,
                )
                time.sleep(min(wait, 30))
                continue

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as exc:
            last_error = exc
            logger.warning(
                "HF API error (attempt %d/%d): %s",
                attempt, _MAX_RETRIES, exc,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)
        except httpx.RequestError as exc:
            last_error = exc
            logger.warning(
                "HF API request error (attempt %d/%d): %s",
                attempt, _MAX_RETRIES, exc,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)

    raise RuntimeError(
        f"HuggingFace Inference API failed after {_MAX_RETRIES} attempts: {last_error}"
    )


def generate_embedding(text: str) -> list[float]:
    """Convert one text string into a 384-dimensional vector."""
    if not text.strip():
        raise ValueError("Cannot generate an embedding for empty text")

    result = _call_hf_api({"inputs": text})

    # The API returns a single vector for a single string input
    vector = result if isinstance(result[0], (int, float)) else result[0]
    return _normalize(vector)


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Convert multiple chunks into normalized vectors via the HF Inference API."""
    if not texts:
        return []

    if any(not text.strip() for text in texts):
        raise ValueError("Cannot embed empty text")

    all_vectors: list[list[float]] = []

    # Process in batches to respect API limits
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        result = _call_hf_api({"inputs": batch})
        all_vectors.extend(result)

    return [_normalize(v) for v in all_vectors]
