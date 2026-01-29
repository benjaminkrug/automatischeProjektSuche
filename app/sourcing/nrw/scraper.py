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

    # Search URL with IT category filter
    # Note: Exact parameters may need adjustment based on actual portal structure
    SEARCH_URL = f"{BASE_URL}/VMPSat498/vergabe/index.html"

    # IT-related category codes (portal-specific)
    IT_CATEGORIES = ["72", "48"]  # CPV prefixes for IT

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
                        if should_skip_project(
                            result.get("title", ""),
                            result.get("description", ""),
                        ):
                            logger.debug("Skipping (early filter): %s", result.get("title", "")[:50])
                            continue

                        # Get details if URL available
                        project = await self._get_tender_details(
                            page,
                            result.get("external_id", ""),
                            result.get("url", ""),
                            result,
                        )
                        if project:
                            projects.append(project)

                        await asyncio.sleep(settings.scraper_delay_seconds)

                    # Navigate to next page
                    if page_num < max_pages:
                        has_next = await self._goto_next_page(page)
                        if not has_next:
                            break

            except Exception as e:
                logger.error("Error scraping NRW portal: %s", e)

        logger.info("NRW: scraped %d tenders", len(projects))
        return projects

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
        """Apply IT category filter on search page."""
        try:
            # Look for category/CPV filter dropdown or input
            filter_selectors = [
                "select[name*='category']",
                "select[name*='cpv']",
                "input[name*='cpv']",
                "#categoryFilter",
                ".category-select",
            ]

            for selector in filter_selectors:
                el = await page.query_selector(selector)
                if el:
                    tag = await el.evaluate("el => el.tagName")

                    if tag.lower() == "select":
                        # Try to select IT category option
                        options = await el.query_selector_all("option")
                        for opt in options:
                            text = (await opt.inner_text()).lower()
                            if any(kw in text for kw in ["it", "software", "dv", "edv", "72"]):
                                value = await opt.get_attribute("value")
                                await el.select_option(value=value)
                                logger.debug("Selected IT category filter")
                                break
                    elif tag.lower() == "input":
                        # Enter CPV code
                        await el.fill("72")
                        await asyncio.sleep(0.5)

                    break

            # Submit search/filter if there's a button
            submit_btn = await page.query_selector(
                "button[type='submit'], input[type='submit'], .search-button"
            )
            if submit_btn:
                await submit_btn.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(1)

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
                # Fill in any missing data from search results
                if not project.client_name:
                    project.client_name = result_data.get("client_name")
                if not project.tender_deadline:
                    project.tender_deadline = result_data.get("deadline")
                if not project.published_at:
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

        Returns:
            True if navigation successful, False if no more pages
        """
        try:
            next_selectors = [
                ".pagination .next:not(.disabled)",
                "a[aria-label='Next']",
                "a[rel='next']",
                ".pager-next a",
                "a:has-text('Weiter')",
                "a:has-text('>')",
            ]

            for selector in next_selectors:
                next_link = await page.query_selector(selector)
                if next_link:
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
