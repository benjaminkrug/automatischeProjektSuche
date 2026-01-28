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

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def _build_search_params(self) -> dict:
        """Build search parameters with team-based keywords.

        Note: Freelancermap treats multiple space-separated keywords as AND search,
        so we only use the first keyword to avoid empty results.
        """
        from app.sourcing.search_config import get_search_keywords

        keywords = get_search_keywords()
        # Freelancermap: Nur erstes Keyword, da AND-Verknüpfung
        query = keywords[0] if keywords else ""
        return {
            "projektart": "1",  # Projektbasiert
            "categories[]": "1",  # IT & Development
            "query": query,  # Einzelnes Keyword für präzise Suche
            "sort": "date",  # Newest first (by date)
        }

    @property
    def SEARCH_PARAMS(self) -> dict:
        """Dynamic search params property for backward compatibility."""
        return self._build_search_params()

    def is_public_sector(self) -> bool:
        return False

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape IT projects from freelancermap.de with multi-keyword search.

        Führt mehrere Suchdurchläufe mit verschiedenen Keywords durch und
        dedupliziert die Ergebnisse für mehr Projektvielfalt.

        Args:
            max_pages: Maximum number of result pages to scrape per keyword

        Returns:
            List of RawProject objects
        """
        from app.sourcing.search_config import get_search_keywords

        # Hole rotierte Keywords (max 4 für Multi-Keyword-Suche)
        keywords = get_search_keywords(max_keywords=4)
        logger.info("Multi-keyword search with: %s", keywords)

        all_projects = []
        seen_ids: set[str] = set()

        async with self._browser_manager.page_context() as page:
            # Handle cookie consent once at the start
            first_url = self._build_search_url_for_keyword(keywords[0] if keywords else "")
            try:
                await page.goto(
                    first_url,
                    wait_until="domcontentloaded",
                    timeout=settings.scraper_timeout_ms,
                )
                await self._handle_cookie_consent(page)
            except Exception as e:
                logger.error("Error loading initial page: %s", e)
                return all_projects

            # Scrape für jedes Keyword separat
            pages_per_keyword = max(1, max_pages // len(keywords)) if keywords else max_pages
            for keyword in keywords:
                search_url = self._build_search_url_for_keyword(keyword)
                logger.debug("Searching for keyword '%s': %s", keyword, search_url)

                keyword_results = await self._scrape_single_keyword(
                    page, search_url, pages_per_keyword
                )

                # Deduplizieren basierend auf external_id
                for result in keyword_results:
                    if result["external_id"] not in seen_ids:
                        seen_ids.add(result["external_id"])
                        all_projects.append(result)

                # Kurze Pause zwischen Keywords
                await asyncio.sleep(1)

            logger.debug("Collected %d unique projects from search, fetching details...", len(all_projects))

            # Now fetch detail pages for all collected results
            projects = []
            for result in all_projects:
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

    async def _scrape_single_keyword(
        self, page, search_url: str, max_pages: int
    ) -> List[dict]:
        """Scrape search results for a single keyword.

        Args:
            page: Playwright page
            search_url: Search URL with keyword
            max_pages: Maximum pages to scrape

        Returns:
            List of result dicts with external_id, url, title
        """
        results = []

        try:
            await page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )
        except Exception as e:
            logger.warning("Error loading search page %s: %s", search_url, e)
            return results

        for page_num in range(1, max_pages + 1):
            logger.debug("Scraping search page %d...", page_num)

            # Parse search results
            page_results = await parse_search_results(page)
            if not page_results:
                logger.debug("No results on page %d", page_num)
                break

            logger.debug("Found %d projects on page %d", len(page_results), page_num)

            # Filter and collect results
            for result in page_results:
                # Early filter on title only (description not available yet)
                if should_skip_project(result["title"], ""):
                    logger.debug("Skipping (early filter): %s", result["title"][:50])
                    continue
                results.append(result)

            # Navigate to next page
            if page_num < max_pages:
                has_next = await self._goto_next_page(page, page_num + 1)
                if not has_next:
                    break
                await asyncio.sleep(1)  # Brief pause between pages

        return results

    def _build_search_url_for_keyword(self, keyword: str) -> str:
        """Build search URL for a specific keyword.

        Args:
            keyword: Single search keyword

        Returns:
            Complete search URL
        """
        params = {
            "projektart": "1",  # Projektbasiert
            "categories[]": "1",  # IT & Development
            "query": keyword,
            "sort": "date",  # Newest first
        }
        return f"{self.SEARCH_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

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
