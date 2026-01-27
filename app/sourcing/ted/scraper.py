"""Scraper for TED (Tenders Electronic Daily) - EU public procurement."""

import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.ted.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.ted")

# Filter settings
PUBLICATION_DATE_RANGE_DAYS = 30  # Only tenders from last 30 days


class TedScraper(BaseScraper):
    """Scraper for TED EU public procurement tenders."""

    source_name = "ted"

    BASE_URL = "https://ted.europa.eu"
    # Search for IT services using CPV codes 72000000 (IT services)
    SEARCH_URL = f"{BASE_URL}/en/search/result"

    SEARCH_PARAMS = {
        "q": "cpv:72000000",  # IT and related services
        "country": "DE",  # Germany
        "sortField": "PD",  # Publication date
        "sortOrder": "desc",
    }

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        return True  # TED is always public sector

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape IT tenders from TED.

        Args:
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []

        async with self._browser_manager.page_context() as page:
            search_url = self._build_search_url()
            logger.debug("Navigating to %s", search_url)

            try:
                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=settings.scraper_timeout_ms,
                )
            except Exception as e:
                logger.error("Error loading search page: %s", e)
                return projects

            # Handle cookie consent
            await self._handle_cookie_consent(page)

            # Wait for dynamic content
            await asyncio.sleep(2)

            for page_num in range(1, max_pages + 1):
                logger.debug("Scraping page %d...", page_num)

                results = await parse_search_results(page)
                if not results:
                    logger.debug("No results on page %d", page_num)
                    break

                logger.debug("Found %d tenders on page %d", len(results), page_num)

                for result in results:
                    # Country filter - TED shows country in title (e.g., "12345-2026 Germany — ...")
                    title = result["title"]
                    if not self._is_german_tender(title):
                        logger.debug("Skipping (not German): %s", title[:50])
                        continue

                    # Early filter - skip obviously unsuitable projects
                    if should_skip_project(title, result.get("description", "")):
                        logger.debug("Skipping (early filter): %s", title[:50])
                        continue

                    project = await self._get_tender_details(
                        page,
                        result["external_id"],
                        result["url"],
                        result["title"],
                    )
                    if project:
                        projects.append(project)

                    await asyncio.sleep(settings.scraper_delay_seconds)

                if page_num < max_pages:
                    has_next = await self._goto_next_page(page, page_num + 1)
                    if not has_next:
                        break

        logger.info("Total scraped: %d tenders", len(projects))
        return projects

    def _is_german_tender(self, title: str) -> bool:
        """Check if tender is from Germany based on title.

        TED titles format: "12345-2026 Country — Description..."
        The country is the second word after the notice ID.

        Args:
            title: Tender title from search results

        Returns:
            True if tender is from Germany
        """
        parts = title.split()
        if len(parts) < 2:
            return False

        # Country is the second word (after ID like "12345-2026")
        country = parts[1].lower().rstrip("—–-")
        return country in ["germany", "deutschland"]

    def _build_search_url(self, page: int = 1) -> str:
        """Build search URL with parameters including date filter."""
        params = [f"{k}={v}" for k, v in self.SEARCH_PARAMS.items()]

        # Add date range filter - only tenders from last N days
        date_from = (datetime.now() - timedelta(days=PUBLICATION_DATE_RANGE_DAYS)).strftime("%Y-%m-%d")
        params.append(f"publicationDateFrom={date_from}")

        if page > 1:
            params.append(f"page={page}")
        return f"{self.SEARCH_URL}?{'&'.join(params)}"

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup."""
        try:
            consent_btn = await page.query_selector(
                "button:has-text('Accept'), "
                "button:has-text('Accept all'), "
                ".cookie-consent-accept, "
                "#cookie-accept"
            )
            if consent_btn:
                await consent_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

    async def _get_tender_details(
        self,
        page,
        external_id: str,
        url: str,
        title: str,
    ) -> Optional[RawProject]:
        """Navigate to tender detail page and extract info."""
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )

            await asyncio.sleep(1)
            project = await parse_detail_page(page, external_id, url)

            if project and not project.title:
                project.title = title

            return project

        except Exception as e:
            logger.warning("Error getting details for %s: %s", external_id, e)
            return RawProject(
                source="ted",
                external_id=external_id,
                url=url,
                title=title,
                public_sector=True,
            )

    async def _goto_next_page(self, page, next_page_num: int) -> bool:
        """Navigate to next results page."""
        try:
            next_link = await page.query_selector(
                ".pagination .next:not(.disabled), "
                "a[aria-label='Next page'], "
                f"a[href*='page={next_page_num}']"
            )
            if next_link:
                await next_link.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)
                return True
        except Exception:
            pass

        return False


async def run_ted_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run TED scraper."""
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = TedScraper()
        return await scraper.scrape(max_pages=max_pages)
