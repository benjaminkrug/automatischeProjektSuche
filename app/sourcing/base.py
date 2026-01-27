"""Base classes for portal scrapers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawProject:
    """Raw project data from scraping (portal-agnostic format)."""
    source: str
    external_id: str
    url: str
    title: str
    client_name: str | None = None
    description: str | None = None
    skills: list[str] = field(default_factory=list)
    budget: str | None = None
    location: str | None = None
    remote: bool = False
    public_sector: bool = False
    deadline: datetime | None = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    # Publication date (when the project/tender was published on the portal)
    published_at: datetime | None = None
    # PDF analysis fields
    pdf_text: str | None = None
    pdf_urls: list[str] = field(default_factory=list)
    # Project type (freelance or tender)
    project_type: str = "freelance"
    # Tender-specific fields
    cpv_codes: list[str] = field(default_factory=list)
    budget_min: int | None = None
    budget_max: int | None = None
    tender_deadline: datetime | None = None


class BaseScraper(ABC):
    """Abstract base class for portal scrapers."""

    source_name: str = "unknown"

    @property
    def is_enabled(self) -> bool:
        """Check if this scraper is enabled in search_config.

        Returns:
            True if scraper is enabled, False otherwise
        """
        from app.sourcing.search_config import is_portal_enabled
        return is_portal_enabled(self.source_name)

    @abstractmethod
    async def scrape(self, max_pages: int = 5) -> list[RawProject]:
        """Scrape projects from the portal.

        Args:
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of RawProject objects
        """
        pass

    def is_public_sector(self) -> bool:
        """Check if this portal is public sector."""
        return False
