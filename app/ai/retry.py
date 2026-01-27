"""Retry-Logik für AI-API-Calls."""

import logging

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from openai import RateLimitError, APITimeoutError, APIConnectionError

from app.core.logging import get_logger

logger = get_logger("ai.retry")

# Decorator für LLM-Calls
# - Max 3 Versuche
# - Exponential Backoff: 2s, 4s, 8s... (max 60s)
# - Retry bei Rate Limits, Timeouts, Connection Errors
llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(
        (
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
        )
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
