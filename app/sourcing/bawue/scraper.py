"""Scraper for Baden-Württemberg Vergabeportal (vergabe.landbw.de).

Scrapes IT tenders from Baden-Württemberg with strong IT/Automotive sector.
Uses Playwright for dynamic content rendering.
"""

import asyncio
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.bawue.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.bawue")


class BawueScraper(BaseScraper):
    """Scraper for Baden-Württemberg Vergabeportal (vergabe.landbw.de)."""

    source_name = "bawue"

    BASE_URL = "https://vergabe.landbw.de"

    # Search URL - Ausschreibungen (InvitationToTender), alle Rechtsrahmen
    SEARCH_URL = f"{BASE_URL}/NetServer/PublicationSearchControllerServlet?function=SearchPublications&Gesetzesgrundlage=All&Category=InvitationToTender"

    def __init__(self):
        """Initialize scraper."""
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        """Always public sector."""
        return True

    async def scrape(self, max_pages: int = 3) -> List[RawProject]:
        """Scrape IT tenders from BaWü portal.

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
                        # Apply early filter with CPV codes (public sector IT)
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
                logger.error("Error scraping BaWü portal: %s", e)

        logger.info("BaWü: scraped %d tenders", len(projects))
        return projects

    def _create_project_from_result(self, result: dict) -> Optional[RawProject]:
        """Create RawProject directly from search result data.

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
            external_id = f"bawue_{hashlib.md5(title.encode()).hexdigest()[:12]}"

        return RawProject(
            source="bawue",
            external_id=external_id,
            url=result.get("url", self.BASE_URL),
            title=title,
            client_name=result.get("client_name"),
            description=result.get("description"),
            public_sector=True,
            project_type="tender",
            cpv_codes=["72000000-5"],  # IT-Dienstleistungen
            tender_deadline=result.get("deadline"),
            published_at=result.get("published_at"),
        )

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
        """Navigate to the public tenders search page.

        BaWü portal structure:
        - Uses PublicationSearchControllerServlet with parameters
        - Category: InvitationToTender for active tenders
        - Gesetzesgrundlage: VOL (Lieferungen/Dienstleistungen), VOB (Bau), All
        """
        try:
            # First try direct navigation to search URL
            await page.goto(
                self.SEARCH_URL,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )
            await asyncio.sleep(1)

            # If we ended up on a login page, look for public access link
            public_links = [
                "a[href*='InvitationToTender']",
                "a:has-text('Ausschreibungen')",
                "a:has-text('Bekanntmachungen')",
                "a:has-text('Öffentliche Ausschreibungen')",
            ]

            for selector in public_links:
                link = await page.query_selector(selector)
                if link:
                    await link.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(1)
                    logger.debug("Navigated to public tenders page")
                    return

        except Exception as e:
            logger.debug("Could not navigate to search: %s", e)

    async def _apply_it_filter(self, page) -> None:
        """Apply IT category filter.

        BaWü portal uses URL parameters for filtering:
        - Gesetzesgrundlage=VOL for services (including IT)
        - No direct CPV filter in UI, filtering done post-scrape
        """
        try:
            # Try to filter by VOL (Liefer-/Dienstleistungen) which includes IT
            vol_link = await page.query_selector(
                "a[href*='Gesetzesgrundlage=VOL']"
            )
            if vol_link:
                await vol_link.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(1)
                logger.debug("Filtered to VOL (Dienstleistungen)")
                return

            # Alternative: Look for category/CPV filter elements
            filter_selectors = [
                "select[name*='category']",
                "select[name*='cpv']",
                "input[name*='cpv']",
                "input[type='search']",
            ]

            for selector in filter_selectors:
                el = await page.query_selector(selector)
                if el:
                    tag = await el.evaluate("el => el.tagName")

                    if tag.lower() == "select":
                        options = await el.query_selector_all("option")
                        for opt in options:
                            text = (await opt.inner_text()).lower()
                            if any(kw in text for kw in ["it", "software", "dv", "72", "dienstleistung"]):
                                value = await opt.get_attribute("value")
                                await el.select_option(value=value)
                                logger.debug("Selected IT category")
                                break
                    elif tag.lower() == "input":
                        await el.fill("Software IT")
                        await asyncio.sleep(0.5)

                    break

            # Submit if button present
            submit_btn = await page.query_selector(
                "button[type='submit'], input[type='submit'], .search-btn, button:has-text('Suchen')"
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
                source="bawue",
                external_id=external_id or f"bawue_{datetime.now().timestamp()}",
                url=self.BASE_URL,
                title=result_data.get("title", "BaWü Ausschreibung"),
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
                source="bawue",
                external_id=external_id or f"bawue_{datetime.now().timestamp()}",
                url=url,
                title=result_data.get("title", "BaWü Ausschreibung"),
                client_name=result_data.get("client_name"),
                description=result_data.get("description"),
                public_sector=True,
                project_type="tender",
                tender_deadline=result_data.get("deadline"),
                published_at=result_data.get("published_at"),
            )

    async def _goto_next_page(self, page) -> bool:
        """Navigate to next results page.

        BaWü portal uses Start parameter for pagination:
        - Start=0 (page 1), Start=50 (page 2), Start=100 (page 3), etc.

        Returns:
            True if successful, False if no more pages
        """
        try:
            # Get current URL to determine next page
            current_url = page.url

            # BaWü uses pagination links with Start parameter
            next_selectors = [
                ".pagination a[href*='Start=']:not(.active)",
                ".pagination-sm a[href*='Start=']",
                "a[rel='next']",
                "a:has-text('>')",
                "a:has-text('Weiter')",
                "a:has-text('»')",
            ]

            for selector in next_selectors:
                links = await page.query_selector_all(selector)
                for link in links:
                    href = await link.get_attribute("href") or ""
                    # Check if this is the next page (higher Start value)
                    if "Start=" in href:
                        current_start = 0
                        if "Start=" in current_url:
                            match = re.search(r"Start=(\d+)", current_url)
                            if match:
                                current_start = int(match.group(1))

                        next_match = re.search(r"Start=(\d+)", href)
                        if next_match:
                            next_start = int(next_match.group(1))
                            if next_start > current_start:
                                await link.click()
                                await page.wait_for_load_state("domcontentloaded")
                                await asyncio.sleep(2)
                                return True

            # Fallback: standard next selectors
            for selector in [".pagination .next:not(.disabled) a", "a[aria-label='Nächste']"]:
                next_link = await page.query_selector(selector)
                if next_link:
                    await next_link.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(2)
                    return True

        except Exception:
            pass

        return False


async def run_bawue_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run BaWü scraper.

    Args:
        max_pages: Maximum pages to scrape

    Returns:
        List of RawProject objects
    """
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = BawueScraper()
        return await scraper.scrape(max_pages=max_pages)
