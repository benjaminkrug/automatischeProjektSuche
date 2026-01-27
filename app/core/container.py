"""Dependency injection container."""

from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.ai_service import AIService
from app.services.embedding_service import EmbeddingService
from app.settings import Settings, settings as default_settings

logger = get_logger("core.container")


@dataclass
class ApplicationContainer:
    """Container for application dependencies.

    Provides centralized dependency management and injection.
    """

    settings: Settings = field(default_factory=lambda: default_settings)
    _openai_client: Optional[OpenAI] = field(default=None, repr=False)
    _embedding_service: Optional[EmbeddingService] = field(default=None, repr=False)
    _ai_service: Optional[AIService] = field(default=None, repr=False)
    _db_session: Optional[Session] = field(default=None, repr=False)

    @classmethod
    def create(cls, settings: Optional[Settings] = None) -> "ApplicationContainer":
        """Create a new application container.

        Args:
            settings: Optional settings override

        Returns:
            Configured ApplicationContainer instance
        """
        container = cls(settings=settings or default_settings)
        logger.debug("Created ApplicationContainer")
        return container

    @property
    def openai_client(self) -> OpenAI:
        """Get OpenAI client (lazy initialization)."""
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=self.settings.openai_api_key)
        return self._openai_client

    @property
    def embedding_service(self) -> EmbeddingService:
        """Get embedding service (lazy initialization)."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService(
                openai_client=self.openai_client,
                settings=self.settings,
            )
        return self._embedding_service

    @property
    def ai_service(self) -> AIService:
        """Get AI service (lazy initialization)."""
        if self._ai_service is None:
            self._ai_service = AIService(settings=self.settings)
        return self._ai_service

    def get_db_session(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy Session instance
        """
        return SessionLocal()

    def close(self) -> None:
        """Clean up container resources."""
        if self._db_session is not None:
            self._db_session.close()
            self._db_session = None
        logger.debug("ApplicationContainer closed")


# Global container instance
_container: Optional[ApplicationContainer] = None


def get_container() -> ApplicationContainer:
    """Get or create the global application container.

    Returns:
        ApplicationContainer instance
    """
    global _container
    if _container is None:
        _container = ApplicationContainer.create()
    return _container


def reset_container() -> None:
    """Reset the global container (useful for testing)."""
    global _container
    if _container is not None:
        _container.close()
        _container = None
