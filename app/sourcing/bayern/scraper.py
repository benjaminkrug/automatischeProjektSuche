"""Scraper for Bayern Vergabeportal (vergabe.bayern.de).

Scrapes IT tenders from Bavaria, Germany's state with strong tech sector.
Uses Playwright for dynamic content rendering.
"""

import asyncio
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.bayern.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.bayern")


class BayernScraper(BaseScraper):
    """Scraper for Bayern Vergabeportal (vergabe.bayern.de)."""

    source_name = "bayern"

    BASE_URL = "https://www.vergabe.bayern.de"

    # Search URL - actual path may vary
    SEARCH_URL = f"{BASE_URL}/NetServer/PublicationSearchControllerServlet"

    def __init__(self):
        """Initialize scraper."""
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        """Always public sector."""
        return True

    async def scrape(self, max_pages: int = 3) -> List[RawProject]:
        """Scrape IT tenders from Bayern portal.

        Args:
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []

        async with self._browser_manager.page_context() as page:
            try:
                # Navigate to search page
                logger.debug("Navigating to %s", self.BASE_URL)
                await page.goto(
                    self.BASE_URL,
                    wait_until="domcontentloaded",
                    timeout=settings.scraper_timeout_ms,
                )

                # Handle cookie consent
                await self._handle_cookie_consent(page)

                # Navigate to public tenders
                await self._navigate_to_search(page)

                # Apply IT filter
                await self._apply_it_filter(page)

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

                        # Get details
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
                logger.error("Error scraping Bayern portal: %s", e)

        logger.info("Bayern: scraped %d tenders", len(projects))
        return projects

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup."""
        try:
            consent_selectors = [
                "button:has-text('Akzeptieren')",
                "button:has-text('Alle akzeptieren')",
                "button:has-text('Zustimmen')",
                ".cookie-accept",
                "#acceptCookies",
            ]

            for selector in consent_selectors:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
                    logger.debug("Accepted cookie consent")
                    break

        except Exception:
            pass

    async def _navigate_to_search(self, page) -> None:
        """Navigate to the public tenders search page."""
        try:
            # Look for link to public tenders
            search_selectors = [
                "a:has-text('Ausschreibungen')",
                "a:has-text('Bekanntmachungen')",
                "a:has-text('Öffentliche Ausschreibungen')",
                "a:has-text('Suche')",
                "a[href*='search']",
                "a[href*='publikation']",
            ]

            for selector in search_selectors:
                link = await page.query_selector(selector)
                if link:
                    await link.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(1)
                    logger.debug("Navigated to search page")
                    return

            # If no link found, try direct URL
            await page.goto(
                self.SEARCH_URL,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )

        except Exception as e:
            logger.debug("Could not navigate to search: %s", e)

    async def _apply_it_filter(self, page) -> None:
        """Apply IT category filter."""
        try:
            # Look for category/CPV filter
            filter_selectors = [
                "select[name*='category']",
                "select[name*='cpv']",
                "input[name*='cpv']",
                "#categoryFilter",
                "select[name*='branche']",
            ]

            for selector in filter_selectors:
                el = await page.query_selector(selector)
                if el:
                    tag = await el.evaluate("el => el.tagName")

                    if tag.lower() == "select":
                        options = await el.query_selector_all("option")
                        for opt in options:
                            text = (await opt.inner_text()).lower()
                            if any(kw in text for kw in ["it", "software", "dv", "72"]):
                                value = await opt.get_attribute("value")
                                await el.select_option(value=value)
                                logger.debug("Selected IT category")
                                break
                    elif tag.lower() == "input":
                        await el.fill("72")
                        await asyncio.sleep(0.5)

                    break

            # Submit search
            submit_btn = await page.query_selector(
                "button[type='submit'], input[type='submit'], .search-btn, #searchButton"
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
        """Get tender details from detail page.

        Args:
            page: Playwright page
            external_id: Tender ID
            url: Detail page URL
            result_data: Data from search results

        Returns:
            RawProject or None
        """
        # Create basic project if no URL
        if not url:
            return RawProject(
                source="bayern",
                external_id=external_id or f"bayern_{datetime.now().timestamp()}",
                url=self.BASE_URL,
                title=result_data.get("title", "Bayern Ausschreibung"),
                client_name=result_data.get("client_name"),
                description=result_data.get("description"),
                public_sector=True,
                project_type="tender",
                tender_deadline=result_data.get("deadline"),
                published_at=result_data.get("published_at"),
            )

        try:
            full_url = url if url.startswith("http") else urljoin(self.BASE_URL, url)
            await page.goto(
                full_url,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )

            project = await parse_detail_page(page, external_id, full_url)

            if project:
                # Fill missing data
                if not project.client_name:
                    project.client_name = result_data.get("client_name")
                if not project.tender_deadline:
                    project.tender_deadline = result_data.get("deadline")
                if not project.published_at:
                    project.published_at = result_data.get("published_at")

            return project

        except Exception as e:
            logger.warning("Error getting details for %s: %s", external_id, e)
            return RawProject(
                source="bayern",
                external_id=external_id or f"bayern_{datetime.now().timestamp()}",
                url=url,
                title=result_data.get("title", "Bayern Ausschreibung"),
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
            True if successful, False if no more pages
        """
        try:
            next_selectors = [
                ".pagination .next:not(.disabled)",
                "a[aria-label='Nächste']",
                "a[rel='next']",
                ".pager-next a",
                "a:has-text('Weiter')",
                "a:has-text('»')",
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


async def run_bayern_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run Bayern scraper.

    Args:
        max_pages: Maximum pages to scrape

    Returns:
        List of RawProject objects
    """
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = BayernScraper()
        return await scraper.scrape(max_pages=max_pages)
