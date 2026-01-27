"""Generate embeddings using OpenAI API.

This module provides backwards compatibility with the old interface.
For new code, use app.services.embedding_service instead.
"""

from typing import List

from app.core.logging import get_logger
from app.services.embedding_service import (
    EmbeddingService,
    create_embedding,
    create_embeddings_batch,
    get_embedding_service,
)

logger = get_logger("team.embedding")

# Re-export for backwards compatibility
__all__ = [
    "create_embedding",
    "create_embeddings_batch",
    "get_embedding_service",
    "EmbeddingService",
]


def get_openai_client():
    """Get OpenAI client (backwards compatibility).

    Deprecated: Use get_embedding_service() instead.
    """
    logger.debug("get_openai_client() called - consider using get_embedding_service()")
    return get_embedding_service()._client
