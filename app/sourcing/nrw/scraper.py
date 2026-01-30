"""Scraper for NRW Vergabeportal (evergabe.nrw.de).

Scrapes IT tenders from North Rhine-Westphalia, Germany's most populous state.
Uses Playwright for dynamic content rendering.
"""

import asyncio
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin, urlencode

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.nrw.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.nrw")


class NrwScraper(BaseScraper):
    """Scraper for NRW Vergabeportal (evergabe.nrw.de)."""

    source_name = "nrw"

    BASE_URL = "https://www.evergabe.nrw.de"

    # Search URL - direkt IT-Dienstleistungen (CPV 72000000-5)
    SEARCH_URL = f"{BASE_URL}/VMPCenter/company/announcements/categoryOverview.do?method=showTable&cpvCode=72000000-5"

    # IT-related CPV category codes
    IT_CPV_CODES = ["72000000-5"]  # IT-Dienstleistungen

    def __init__(self):
        """Initialize scraper."""
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        """Always public sector."""
        return True

    async def scrape(self, max_pages: int = 3) -> List[RawProject]:
        """Scrape IT tenders from NRW portal.

        Args:
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []

        async with self._browser_manager.page_context() as page:
            try:
                # Navigate to search page
                logger.debug("Navigating to %s", self.SEARCH_URL)
                await page.goto(
                    self.SEARCH_URL,
                    wait_until="domcontentloaded",
                    timeout=settings.scraper_timeout_ms,
                )

                # Handle cookie consent if present
                await self._handle_cookie_consent(page)

                # Apply IT filter
                await self._apply_it_filter(page)

                # Wait for results
                await asyncio.sleep(2)

                for page_num in range(1, max_pages + 1):
                    logger.debug("Scraping page %d...", page_num)

                    results = await parse_search_results(page)
                    if not results:
                        logger.debug("No results on page %d", page_num)
                        break

                    logger.debug("Found %d tenders on page %d", len(results), page_num)

                    for result in results:
                        # Apply early filter
                        # Pass CPV codes since we're already on IT category page
                        if should_skip_project(
                            result.get("title", ""),
                            result.get("description", ""),
                            cpv_codes=["72000000-5"],  # IT-Dienstleistungen
                        ):
                            logger.debug("Skipping (early filter): %s", result.get("title", "")[:50])
                            continue

                        # Create project directly from search results
                        # (Detail page navigation is slow and causes state loss)
                        project = self._create_project_from_result(result)
                        if project:
                            projects.append(project)

                    # Navigate to next page
                    if page_num < max_pages:
                        has_next = await self._goto_next_page(page)
                        if not has_next:
                            break

            except Exception as e:
                logger.error("Error scraping NRW portal: %s", e)

        logger.info("NRW: scraped %d tenders", len(projects))
        return projects

    def _create_project_from_result(self, result: dict) -> Optional[RawProject]:
        """Create RawProject directly from search result data.

        This is faster than navigating to detail pages and avoids
        browser state issues.

        Args:
            result: Dictionary with parsed search result data

        Returns:
            RawProject or None
        """
        title = result.get("title", "").strip()
        if not title or len(title) < 5:
            return None

        external_id = result.get("external_id", "")
        if not external_id:
            import hashlib
            external_id = f"nrw_{hashlib.md5(title.encode()).hexdigest()[:12]}"

        return RawProject(
            source="nrw",
            external_id=external_id,
            url=result.get("url", self.BASE_URL),
            title=title,
            client_name=result.get("client_name"),
            description=result.get("description"),
            public_sector=True,
            project_type="tender",
            cpv_codes=["72000000-5"],  # IT-Dienstleistungen (from search filter)
            tender_deadline=result.get("deadline"),
            published_at=result.get("published_at"),
        )

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup if present."""
        try:
            consent_selectors = [
                "button:has-text('Akzeptieren')",
                "button:has-text('Alle akzeptieren')",
                "button:has-text('Accept')",
                ".cookie-accept",
                "#cookie-accept",
                "[data-cookie-accept]",
            ]

            for selector in consent_selectors:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
                    logger.debug("Accepted cookie consent")
                    break

        except Exception:
            pass  # No consent popup or already accepted

    async def _apply_it_filter(self, page) -> None:
        """Apply IT category filter on search page.

        NRW portal uses CPV category links like:
        a[href*="categoryOverview.do?cpvCode=72"]
        """
        try:
            # Method 1: Click on CPV 72 (IT-Dienstleistungen) category link
            cpv_link = await page.query_selector(
                "a[href*='cpvCode=72'], a[href*='cpv=72']"
            )
            if cpv_link:
                await cpv_link.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(1)
                logger.debug("Selected CPV 72 (IT) category via link")
                return

            # Method 2: Use search text field
            search_input = await page.query_selector(
                "input[name='searchText'], #searchText"
            )
            if search_input:
                await search_input.fill("Software IT Entwicklung")
                await asyncio.sleep(0.5)

            # Method 3: Use CPV input field if available
            cpv_input = await page.query_selector(
                "[data-extended-cpvbox] input, input[name*='cpv']"
            )
            if cpv_input:
                await cpv_input.fill("72")
                await asyncio.sleep(0.5)

            # Submit search form
            submit_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "#searchButton",
                "button:has-text('Suchen')",
            ]
            for selector in submit_selectors:
                submit_btn = await page.query_selector(selector)
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(1)
                    logger.debug("Submitted search form")
                    break

        except Exception as e:
            logger.debug("Could not apply IT filter: %s", e)

    async def _get_tender_details(
        self,
        page,
        external_id: str,
        url: str,
        result_data: dict,
    ) -> Optional[RawProject]:
        """Navigate to detail page and extract information.

        Args:
            page: Playwright page
            external_id: Tender ID
            url: Detail page URL
            result_data: Data already parsed from search results

        Returns:
            RawProject or None
        """
        # If no URL, create basic project from search data
        if not url:
            return RawProject(
                source="nrw",
                external_id=external_id or f"nrw_{datetime.now().timestamp()}",
                url=self.BASE_URL,
                title=result_data.get("title", "NRW Ausschreibung"),
                client_name=result_data.get("client_name"),
                description=result_data.get("description"),
                public_sector=True,
                project_type="tender",
                tender_deadline=result_data.get("deadline"),
                published_at=result_data.get("published_at"),
            )

        try:
            # Navigate to detail page
            full_url = url if url.startswith("http") else urljoin(self.BASE_URL, url)
            await page.goto(
                full_url,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )

            # Parse detail page
            project = await parse_detail_page(page, external_id, full_url)

            if project:
                # IMPORTANT: Prefer data from search results over detail page
                # Detail pages often redirect and have navigation elements as titles
                search_title = result_data.get("title", "")
                if search_title and len(search_title) > 10:
                    # Keep search result title if it's meaningful
                    project.title = search_title
                if result_data.get("client_name"):
                    project.client_name = result_data.get("client_name")
                if result_data.get("deadline"):
                    project.tender_deadline = result_data.get("deadline")
                if result_data.get("published_at"):
                    project.published_at = result_data.get("published_at")

            return project

        except Exception as e:
            logger.warning("Error getting details for %s: %s", external_id, e)
            # Return basic project from search data
            return RawProject(
                source="nrw",
                external_id=external_id or f"nrw_{datetime.now().timestamp()}",
                url=url,
                title=result_data.get("title", "NRW Ausschreibung"),
                client_name=result_data.get("client_name"),
                description=result_data.get("description"),
                public_sector=True,
                project_type="tender",
                tender_deadline=result_data.get("deadline"),
                published_at=result_data.get("published_at"),
            )

    async def _goto_next_page(self, page) -> bool:
        """Navigate to next results page.

        NRW portal uses: #nextPage (aria-label="nächste Seite")

        Returns:
            True if navigation successful, False if no more pages
        """
        try:
            next_selectors = [
                "#nextPage:not([disabled])",
                "a[aria-label='nächste Seite']:not(.disabled)",
                ".pagination .next:not(.disabled)",
                "a[aria-label='Next']",
                "a[rel='next']",
                "a:has-text('Weiter')",
            ]

            for selector in next_selectors:
                next_link = await page.query_selector(selector)
                if next_link:
                    # Check if button is disabled
                    is_disabled = await next_link.get_attribute("disabled")
                    if is_disabled:
                        continue
                    await next_link.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(2)
                    return True

        except Exception:
            pass

        return False


async def run_nrw_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run NRW scraper.

    Args:
        max_pages: Maximum pages to scrape

    Returns:
        List of RawProject objects
    """
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = NrwScraper()
        return await scraper.scrape(max_pages=max_pages)
