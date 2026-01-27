"""Scraper for malt.de project marketplace."""

import asyncio
import re
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.malt.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.malt")


class MaltScraper(BaseScraper):
    """Scraper for malt.de freelance projects."""

    source_name = "malt"

    BASE_URL = "https://www.malt.de"

    # Tech-specific search parameters
    SEARCH_PARAMS = {
        "expertise": "tech",
        "sort": "newest",
    }

    @property
    def SEARCH_URL(self) -> str:
        """Build search URL with tech filter parameters."""
        from urllib.parse import urlencode
        params = urlencode(self.SEARCH_PARAMS)
        return f"{self.BASE_URL}/projects?{params}"

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        return False

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape freelance projects from malt.de.

        Args:
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []

        async with self._browser_manager.page_context() as page:
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

            await self._handle_cookie_consent(page)
            await asyncio.sleep(2)

            for page_num in range(1, max_pages + 1):
                logger.debug("Scraping page %d...", page_num)

                results = await parse_search_results(page)
                if not results:
                    logger.debug("No results on page %d", page_num)
                    break

                logger.debug("Found %d projects on page %d", len(results), page_num)

                for result in results:
                    project = await self._get_project_details(
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

        logger.info("Total scraped: %d projects", len(projects))
        return projects

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup."""
        try:
            consent_btn = await page.query_selector(
                "button:has-text('Akzeptieren'), "
                "button:has-text('Accept'), "
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

            await asyncio.sleep(1)
            project = await parse_detail_page(page, external_id, url)

            if project and not project.title:
                project.title = title

            return project

        except Exception as e:
            logger.warning("Error getting details for %s: %s", external_id, e)
            return RawProject(
                source="malt",
                external_id=external_id,
                url=url,
                title=title,
                public_sector=False,
            )

    async def _goto_next_page(self, page, next_page_num: int) -> bool:
        """Navigate to next results page."""
        try:
            next_link = await page.query_selector(
                ".pagination .next:not(.disabled), "
                "a[aria-label='Next'], "
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


async def run_malt_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run malt scraper."""
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = MaltScraper()
        return await scraper.scrape(max_pages=max_pages)
