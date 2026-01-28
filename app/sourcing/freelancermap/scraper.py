"""Scraper for freelancermap.de project marketplace."""

import asyncio
import re
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.freelancermap.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.freelancermap")


class FreelancermapScraper(BaseScraper):
    """Scraper for freelancermap.de IT projects."""

    source_name = "freelancermap"

    BASE_URL = "https://www.freelancermap.de"
    SEARCH_URL = f"{BASE_URL}/projektboerse.html"

    # Search parameters for IT projects
    SEARCH_PARAMS = {
        "projektart": "1",  # Projektbasiert
        "categories[]": "1",  # IT & Development
        "sort": "date",  # Newest first (by date)
    }

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        return False

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape IT projects from freelancermap.de.

        Args:
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []

        async with self._browser_manager.page_context() as page:
            # Navigate to search page
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

            # Handle cookie consent if present
            await self._handle_cookie_consent(page)

            # First, collect all search results from all pages
            all_results = []
            for page_num in range(1, max_pages + 1):
                logger.debug("Scraping search page %d...", page_num)

                # Parse search results
                results = await parse_search_results(page)
                if not results:
                    logger.debug("No results on page %d", page_num)
                    break

                logger.debug("Found %d projects on page %d", len(results), page_num)

                # Filter and collect results
                for result in results:
                    # Early filter on title only (description not available yet)
                    if should_skip_project(result["title"], ""):
                        logger.debug("Skipping (early filter): %s", result["title"][:50])
                        continue
                    all_results.append(result)

                # Navigate to next page
                if page_num < max_pages:
                    has_next = await self._goto_next_page(page, page_num + 1)
                    if not has_next:
                        break
                    await asyncio.sleep(1)  # Brief pause between pages

            logger.debug("Collected %d projects from search, fetching details...", len(all_results))

            # Now fetch detail pages for all collected results
            for result in all_results:
                # Fetch detail page for description, skills, etc.
                project = await self._get_project_details(
                    page,
                    result["external_id"],
                    result["url"],
                    result["title"],
                )

                if project:
                    # Apply early filter again with full description
                    if should_skip_project(project.title, project.description or ""):
                        logger.debug("Skipping (early filter after details): %s", project.title[:50])
                        continue
                    projects.append(project)

                # Brief pause between detail page requests to avoid rate limiting
                await asyncio.sleep(0.5)

        logger.info("Total scraped: %d projects", len(projects))
        return projects

    def _build_search_url(self, page: int = 1) -> str:
        """Build search URL with parameters."""
        params = [f"{k}={v}" for k, v in self.SEARCH_PARAMS.items()]
        if page > 1:
            params.append(f"pagenr={page}")
        return f"{self.SEARCH_URL}?{'&'.join(params)}"

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup if present."""
        try:
            consent_btn = await page.query_selector(
                "button:has-text('Akzeptieren'), "
                "button:has-text('Alle akzeptieren'), "
                "#onetrust-accept-btn-handler, "
                ".cookie-consent-accept"
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
            project = await parse_detail_page(page, external_id, url)

            # Use title from search if detail parsing failed
            if project and not project.title:
                project.title = title

            return project

        except Exception as e:
            logger.warning("Error getting details for %s: %s", external_id, e)
            # Return minimal project with search data
            return RawProject(
                source="freelancermap",
                external_id=external_id,
                url=url,
                title=title,
                public_sector=False,
            )

    async def _goto_next_page(self, page, next_page_num: int) -> bool:
        """Navigate to next results page."""
        try:
            # Try pagination link
            next_link = await page.query_selector(
                f"a[href*='pagenr={next_page_num}'], "
                f".pagination a:has-text('{next_page_num}'), "
                ".pagination .next, "
                "a[rel='next']"
            )
            if next_link:
                await next_link.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(1)
                return True
        except Exception:
            pass

        return False


async def run_freelancermap_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run freelancermap scraper.

    Args:
        max_pages: Maximum pages to scrape

    Returns:
        List of scraped projects
    """
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = FreelancermapScraper()
        return await scraper.scrape(max_pages=max_pages)
