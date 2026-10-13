"""Small asynchronous Groq Chat Completions adapter."""

import asyncio
import logging
import random
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_ATTEMPTS = 3
CONNECT_TIMEOUT_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 25.0
MAX_RETRY_WAIT_SECONDS = 5.0


class GroqConfigurationError(RuntimeError):
    pass


class GroqProviderError(RuntimeError):
    def __init__(self, category: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.retryable = retryable


@dataclass
class Completion:
    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                delay = max(float(retry_after), 0.0)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    delay = max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0)
                except (TypeError, ValueError, OverflowError):
                    delay = 0.0
            # If the provider asks us to wait longer than the request's retry
            # budget, return the safe retryable error instead of retrying early.
            return delay if delay <= MAX_RETRY_WAIT_SECONDS else None
    return min((0.35 * (2 ** (attempt - 1))) + random.uniform(0.0, 0.2), 2.0)


async def complete(
    messages: list[dict],
    *,
    max_completion_tokens: int = 1400,
    response_format: dict | None = None,
) -> Completion:
    api_key = settings.GROQ_API_KEY.strip()
    model = settings.GROQ_MODEL.strip()
    if not api_key:
        raise GroqConfigurationError(
            "Groq is not configured. Set GROQ_API_KEY in the backend environment."
        )
    if not model:
        raise GroqConfigurationError(
            "Groq model is not configured. Set GROQ_MODEL in the backend environment."
        )

    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT_SECONDS,
        read=READ_TIMEOUT_SECONDS,
        write=5.0,
        pool=3.0,
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_completion_tokens": max_completion_tokens,
    }
    if response_format is not None:
        body["response_format"] = response_format

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(GROQ_CHAT_COMPLETIONS_URL, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            if attempt < MAX_ATTEMPTS:
                logger.warning("Groq request transport failure attempt=%d category=%s", attempt, type(exc).__name__)
                await asyncio.sleep(_retry_delay(None, attempt))
                continue
            raise GroqProviderError("provider_timeout", "Groq took too long to respond. Please retry shortly.", retryable=True) from exc
        except httpx.NetworkError as exc:
            if attempt < MAX_ATTEMPTS:
                logger.warning("Groq request transport failure attempt=%d category=%s", attempt, type(exc).__name__)
                await asyncio.sleep(_retry_delay(None, attempt))
                continue
            raise GroqProviderError("provider_unavailable", "Groq could not be reached. Please retry shortly.", retryable=True) from exc

        if response.status_code in {408, 429} or response.status_code >= 500:
            if attempt < MAX_ATTEMPTS:
                delay = _retry_delay(response, attempt)
                if delay is None:
                    category = "rate_limited" if response.status_code == 429 else "provider_unavailable"
                    raise GroqProviderError(category, "Groq asked us to retry later. Please retry shortly.", retryable=True)
                logger.warning("Groq returned retryable status=%d attempt=%d", response.status_code, attempt)
                await asyncio.sleep(delay)
                continue
            category = "rate_limited" if response.status_code == 429 else "provider_unavailable"
            raise GroqProviderError(category, "Groq is temporarily unavailable. Please retry shortly.", retryable=True)

        if response.status_code in {401, 403}:
            logger.error("Groq authentication failed status=%d; verify backend GROQ_API_KEY", response.status_code)
            raise GroqProviderError("provider_configuration", "Groq rejected the backend API key. Check GROQ_API_KEY.")
        if response.status_code >= 400:
            logger.error("Groq rejected completion status=%d model=%s", response.status_code, model)
            raise GroqProviderError("provider_request_rejected", "Groq rejected this summarization request. Check the configured model and try again.")

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty completion")
            usage = payload.get("usage") or {}
            return Completion(
                content=content.strip(),
                model=str(payload.get("model") or model),
                prompt_tokens=usage.get("prompt_tokens") if isinstance(usage.get("prompt_tokens"), int) else None,
                completion_tokens=usage.get("completion_tokens") if isinstance(usage.get("completion_tokens"), int) else None,
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.error("Groq returned an invalid completion payload model=%s", model)
            raise GroqProviderError("provider_invalid_response", "Groq returned an invalid response. Please retry.") from exc

    raise GroqProviderError("provider_unavailable", "Groq is temporarily unavailable. Please retry shortly.", retryable=True)
