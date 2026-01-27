"""Scraper for LinkedIn Jobs.

Note: LinkedIn requires authentication for full access and has
strict anti-scraping measures. This scraper uses public job listings
which may have limited results. For production use, consider using
LinkedIn's official API with proper authentication.
"""

import asyncio
import re
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.linkedin.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.linkedin")


class LinkedinScraper(BaseScraper):
    """Scraper for LinkedIn job postings.

    Note: LinkedIn has strict anti-scraping policies. This scraper
    accesses public job listings only and may require authentication
    for reliable operation.
    """

    source_name = "linkedin"

    BASE_URL = "https://www.linkedin.com"
    # Public jobs search (no login required for basic access)
    SEARCH_URL = f"{BASE_URL}/jobs/search/"

    # Search parameters for IT/developer jobs in Germany
    SEARCH_PARAMS = {
        "keywords": "Software Developer OR Web Developer OR IT Consultant",
        "location": "Germany",
        "f_JT": "C",  # Contract jobs
        "sortBy": "DD",  # Most recent
    }

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        return False

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape job postings from LinkedIn.

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

            # Wait for content to load
            await asyncio.sleep(3)

            # Check if we're blocked or need login
            if await self._is_blocked(page):
                logger.warning("LinkedIn requires login for full access. Results may be limited.")

            for page_num in range(1, max_pages + 1):
                logger.debug("Scraping page %d...", page_num)

                results = await parse_search_results(page)
                if not results:
                    logger.debug("No results on page %d", page_num)
                    break

                logger.debug("Found %d jobs on page %d", len(results), page_num)

                # Extract from search results to minimize requests
                for result in results:
                    project = RawProject(
                        source="linkedin",
                        external_id=result["external_id"],
                        url=result["url"],
                        title=result["title"],
                        client_name=result.get("company"),
                        description=result.get("description"),
                        location=result.get("location"),
                        remote=result.get("remote", False),
                        public_sector=False,
                    )
                    projects.append(project)

                    await asyncio.sleep(settings.scraper_delay_seconds)

                if page_num < max_pages:
                    has_next = await self._goto_next_page(page)
                    if not has_next:
                        break

        logger.info("Total scraped: %d jobs", len(projects))
        return projects

    def _build_search_url(self, start: int = 0) -> str:
        """Build search URL with parameters."""
        params = [f"{k}={v.replace(' ', '%20')}" for k, v in self.SEARCH_PARAMS.items()]
        if start > 0:
            params.append(f"start={start}")
        return f"{self.SEARCH_URL}?{'&'.join(params)}"

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup."""
        try:
            consent_btn = await page.query_selector(
                "button:has-text('Accept'), "
                "button:has-text('Accept cookies'), "
                "[data-test-id='accept-cookies']"
            )
            if consent_btn:
                await consent_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

    async def _is_blocked(self, page) -> bool:
        """Check if we're blocked or need login."""
        try:
            blocked_indicators = [
                "sign in",
                "log in",
                "join now",
                "authwall",
                "sign up"
            ]
            page_text = await page.inner_text("body")
            return any(indicator in page_text.lower() for indicator in blocked_indicators)
        except Exception:
            return False

    async def _goto_next_page(self, page) -> bool:
        """Navigate to next results page (LinkedIn uses infinite scroll)."""
        try:
            # LinkedIn uses lazy loading, scroll to load more
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

            # Also try pagination button
            next_btn = await page.query_selector(
                "button[aria-label='Next'], "
                ".pagination__next, "
                "[data-test='pagination-next']"
            )
            if next_btn:
                await next_btn.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)
                return True

            # Check if new content loaded via scroll
            return True
        except Exception:
            pass

        return False


async def run_linkedin_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run LinkedIn scraper."""
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = LinkedinScraper()
        return await scraper.scrape(max_pages=max_pages)
