"""Scraper for Upwork.com project marketplace.

Note: Upwork has strong anti-bot measures. This scraper may require
login credentials and/or additional stealth techniques to work reliably.
"""

import asyncio
import re
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.upwork.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.upwork")


class UpworkScraper(BaseScraper):
    """Scraper for Upwork.com freelance jobs.

    Note: Upwork has aggressive anti-bot protection. This scraper
    may have limited success without authentication.
    """

    source_name = "upwork"

    BASE_URL = "https://www.upwork.com"
    SEARCH_URL = f"{BASE_URL}/nx/search/jobs/"

    # Search parameters for developer/IT jobs
    SEARCH_PARAMS = {
        "category2_uid": "531770282580668418",  # Web Development
        "sort": "recency",
    }

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        return False

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape IT jobs from Upwork.

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

            await self._handle_cookie_consent(page)

            # Wait for dynamic content to load
            await asyncio.sleep(3)

            # Check if we're blocked or need login
            if await self._is_blocked(page):
                logger.warning("Upwork appears to be blocking access. Login may be required.")
                return projects

            for page_num in range(1, max_pages + 1):
                logger.debug("Scraping page %d...", page_num)

                results = await parse_search_results(page)
                if not results:
                    logger.debug("No results on page %d", page_num)
                    break

                logger.debug("Found %d jobs on page %d", len(results), page_num)

                # For Upwork, we extract data from search page to avoid anti-bot triggers
                for result in results:
                    project = RawProject(
                        source="upwork",
                        external_id=result["external_id"],
                        url=result["url"],
                        title=result["title"],
                        description=result.get("description"),
                        skills=result.get("skills", []),
                        budget=result.get("budget"),
                        remote=True,  # Upwork is mostly remote
                        public_sector=False,
                    )
                    projects.append(project)

                    await asyncio.sleep(settings.scraper_delay_seconds)

                if page_num < max_pages:
                    has_next = await self._goto_next_page(page, page_num + 1)
                    if not has_next:
                        break

        logger.info("Total scraped: %d jobs", len(projects))
        return projects

    def _build_search_url(self, page: int = 1) -> str:
        """Build search URL with parameters."""
        params = [f"{k}={v}" for k, v in self.SEARCH_PARAMS.items()]
        if page > 1:
            params.append(f"page={page}")
        return f"{self.SEARCH_URL}?{'&'.join(params)}"

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup."""
        try:
            consent_btn = await page.query_selector(
                "button:has-text('Accept'), "
                "button:has-text('Accept Cookies'), "
                "#onetrust-accept-btn-handler"
            )
            if consent_btn:
                await consent_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

    async def _is_blocked(self, page) -> bool:
        """Check if we're blocked by anti-bot measures."""
        try:
            # Look for common blocking indicators
            blocked_indicators = [
                "captcha",
                "verify you are human",
                "access denied",
                "please log in",
                "sign in to continue"
            ]
            page_text = await page.inner_text("body")
            return any(indicator in page_text.lower() for indicator in blocked_indicators)
        except Exception:
            return False

    async def _goto_next_page(self, page, next_page_num: int) -> bool:
        """Navigate to next results page."""
        try:
            next_link = await page.query_selector(
                "button[aria-label='Next'], "
                ".pagination-next:not(.disabled), "
                f"a[href*='page={next_page_num}']"
            )
            if next_link:
                await next_link.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(3)
                return True
        except Exception:
            pass

        return False


async def run_upwork_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run Upwork scraper."""
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = UpworkScraper()
        return await scraper.scrape(max_pages=max_pages)
