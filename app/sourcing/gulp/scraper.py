"""Scraper for gulp.de project marketplace."""

import asyncio
import re
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.gulp.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.gulp")


class GulpScraper(BaseScraper):
    """Scraper for gulp.de IT projects."""

    source_name = "gulp"

    BASE_URL = "https://www.gulp.de"

    # IT-specific search parameters
    SEARCH_PARAMS = {
        "category": "it",
        "q": "Software Entwicklung",
        "sort": "date",
    }

    @property
    def SEARCH_URL(self) -> str:
        """Build search URL with IT filter parameters."""
        from urllib.parse import urlencode
        params = urlencode(self.SEARCH_PARAMS)
        return f"{self.BASE_URL}/gulp2/g/projekte?{params}"

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        return False

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape IT projects from gulp.de.

        Args:
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []

        async with self._browser_manager.page_context() as page:
            # Navigate to search page
            logger.debug("Navigating to %s", self.SEARCH_URL)

            try:
                await page.goto(
                    self.SEARCH_URL,
                    wait_until="domcontentloaded",
                    timeout=settings.scraper_timeout_ms,
                )
            except Exception as e:
                logger.error("Error loading search page: %s", e)
                return projects

            # Handle cookie consent if present
            await self._handle_cookie_consent(page)

            # Wait for dynamic content to load
            await asyncio.sleep(2)

            # Scrape multiple pages - only collect search results, skip detail pages
            for page_num in range(1, max_pages + 1):
                logger.debug("Scraping page %d...", page_num)

                # Parse search results
                results = await parse_search_results(page)
                if not results:
                    logger.debug("No results on page %d", page_num)
                    break

                logger.debug("Found %d projects on page %d", len(results), page_num)

                # Create RawProject from search results (without fetching detail pages)
                for result in results:
                    project = RawProject(
                        source="gulp",
                        external_id=result["external_id"],
                        url=result["url"],
                        title=result["title"],
                        public_sector=False,
                    )
                    projects.append(project)

                # Navigate to next page
                if page_num < max_pages:
                    has_next = await self._goto_next_page(page, page_num + 1)
                    if not has_next:
                        break
                    await asyncio.sleep(1)  # Brief pause between pages

        logger.info("Total scraped: %d projects", len(projects))
        return projects

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup if present."""
        try:
            consent_btn = await page.query_selector(
                "button:has-text('Akzeptieren'), "
                "button:has-text('Alle akzeptieren'), "
                "#onetrust-accept-btn-handler, "
                "[data-testid='cookie-accept']"
            )
            if consent_btn:
                await consent_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

    async def _get_project_details(
        self,
        page,
        external_id: str,
        url: str,
        title: str,
    ) -> Optional[RawProject]:
        """Navigate to project detail page and extract info."""
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )

            # Wait for dynamic content
            await asyncio.sleep(1)

            project = await parse_detail_page(page, external_id, url)

            # Use title from search if detail parsing failed
            if project and not project.title:
                project.title = title

            return project

        except Exception as e:
            logger.warning("Error getting details for %s: %s", external_id, e)
            # Return minimal project with search data
            return RawProject(
                source="gulp",
                external_id=external_id,
                url=url,
                title=title,
                public_sector=False,
            )

    async def _goto_next_page(self, page, next_page_num: int) -> bool:
        """Navigate to next results page."""
        try:
            # GULP uses pagination buttons
            next_link = await page.query_selector(
                ".pagination .next:not(.disabled), "
                "a[aria-label='Nächste Seite'], "
                f"a[href*='page={next_page_num}'], "
                f".pagination a:has-text('{next_page_num}')"
            )
            if next_link:
                await next_link.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)  # Wait for dynamic content
                return True
        except Exception:
            pass

        return False


async def run_gulp_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run gulp scraper.

    Args:
        max_pages: Maximum pages to scrape

    Returns:
        List of scraped projects
    """
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = GulpScraper()
        return await scraper.scrape(max_pages=max_pages)
