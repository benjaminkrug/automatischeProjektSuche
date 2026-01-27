"""Embedding service with retry logic."""

from typing import List, Optional

import tenacity
from openai import OpenAI

from app.core.exceptions import AIProcessingError
from app.core.logging import get_logger
from app.settings import Settings, settings as default_settings

logger = get_logger("services.embedding")


class EmbeddingService:
    """Service for creating text embeddings with retry logic."""

    def __init__(
        self,
        openai_client: Optional[OpenAI] = None,
        settings: Optional[Settings] = None,
    ):
        """Initialize embedding service.

        Args:
            openai_client: Optional OpenAI client instance
            settings: Optional settings instance
        """
        self._settings = settings or default_settings
        self._client = openai_client or OpenAI(api_key=self._settings.openai_api_key)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
        retry=tenacity.retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: logger.warning(
            "Embedding retry attempt %d after error: %s",
            retry_state.attempt_number,
            retry_state.outcome.exception() if retry_state.outcome else "unknown",
        ),
    )
    def create_embedding(self, text: str) -> List[float]:
        """Create embedding vector for text using OpenAI API.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector

        Raises:
            AIProcessingError: If embedding creation fails after retries
        """
        try:
            # Clean and truncate text if needed (max ~8000 tokens)
            text = text.strip()
            if len(text) > 30000:
                text = text[:30000]
                logger.debug("Truncated text to 30000 chars for embedding")

            response = self._client.embeddings.create(
                model=self._settings.embedding_model,
                input=text,
            )

            return response.data[0].embedding

        except Exception as e:
            logger.error("Failed to create embedding: %s", e)
            raise AIProcessingError(
                f"Failed to create embedding: {e}",
                model=self._settings.embedding_model,
            ) from e

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
        retry=tenacity.retry_if_exception_type(Exception),
    )
    def create_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Create embeddings for multiple texts in a single API call.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            AIProcessingError: If batch embedding creation fails after retries
        """
        if not texts:
            return []

        try:
            # Clean texts
            cleaned_texts = [t.strip()[:30000] for t in texts]

            response = self._client.embeddings.create(
                model=self._settings.embedding_model,
                input=cleaned_texts,
            )

            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [d.embedding for d in sorted_data]

        except Exception as e:
            logger.error("Failed to create batch embeddings: %s", e)
            raise AIProcessingError(
                f"Failed to create batch embeddings: {e}",
                model=self._settings.embedding_model,
            ) from e


# Default instance for backwards compatibility
_default_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get default embedding service instance."""
    global _default_service
    if _default_service is None:
        _default_service = EmbeddingService()
    return _default_service


def create_embedding(text: str) -> List[float]:
    """Create embedding using default service (backwards compatible)."""
    return get_embedding_service().create_embedding(text)


def create_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Create batch embeddings using default service (backwards compatible)."""
    return get_embedding_service().create_embeddings_batch(texts)
