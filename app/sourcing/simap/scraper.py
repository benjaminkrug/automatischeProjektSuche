"""Scraper for simap.ch - Swiss public procurement portal."""

import asyncio
import re
from datetime import datetime
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.playwright.browser import get_browser_manager

logger = get_logger("sourcing.simap")


class SimapScraper(BaseScraper):
    """Scraper for simap.ch Swiss public procurement tenders.

    simap.ch is the official Swiss public procurement portal. The site uses
    a React-based SPA, so we use Playwright for browser-based scraping.

    All tenders on simap.ch are public sector by definition.
    """

    source_name = "simap.ch"

    # Main search page URL
    SEARCH_URL = "https://www.simap.ch/de"

    # IT-related CPV codes for filtering
    IT_CPV_PREFIX = "72"  # IT services start with 72

    def __init__(self):
        """Initialize the simap.ch scraper."""
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        """simap.ch is always public sector."""
        return True

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape IT tenders from simap.ch.

        Args:
            max_pages: Maximum number of result pages to fetch

        Returns:
            List of RawProject objects
        """
        logger.info("Starting simap.ch scrape (max_pages=%d)", max_pages)
        projects = []

        async with self._browser_manager.page_context() as page:
            try:
                # Navigate to main page
                logger.debug("Navigating to %s", self.SEARCH_URL)
                await page.goto(
                    self.SEARCH_URL,
                    wait_until="networkidle",
                    timeout=settings.scraper_timeout_ms,
                )

                # Handle cookie consent
                await self._handle_cookie_consent(page)

                # Wait for React app to load
                await asyncio.sleep(3)

                # Try to access search results
                await self._navigate_to_search(page)

                # Scrape results
                for page_num in range(1, max_pages + 1):
                    logger.debug("Scraping page %d...", page_num)

                    page_projects = await self._parse_search_results(page)
                    if not page_projects:
                        logger.debug("No results on page %d", page_num)
                        break

                    projects.extend(page_projects)
                    logger.debug(
                        "Found %d tenders on page %d (total: %d)",
                        len(page_projects),
                        page_num,
                        len(projects),
                    )

                    if page_num < max_pages:
                        has_next = await self._goto_next_page(page)
                        if not has_next:
                            break

                    await asyncio.sleep(settings.scraper_delay_seconds)

            except Exception as e:
                logger.error("Error scraping simap.ch: %s", e)

        logger.info("Total scraped: %d tenders", len(projects))
        return projects

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup if present."""
        try:
            consent_selectors = [
                "button:has-text('Akzeptieren')",
                "button:has-text('Alle akzeptieren')",
                "button:has-text('Accept')",
                "button:has-text('Accept all')",
                "[data-testid='cookie-accept']",
                ".cookie-consent-accept",
            ]

            for selector in consent_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(1)
                        logger.debug("Clicked cookie consent button")
                        return
                except Exception:
                    continue

        except Exception:
            pass

    async def _navigate_to_search(self, page) -> None:
        """Navigate to search results with IT filter if possible."""
        try:
            # Try to find and click on publications/search link
            search_selectors = [
                "a:has-text('Publications')",
                "a:has-text('Publikationen')",
                "a:has-text('Suche')",
                "a:has-text('Search')",
                "[href*='search']",
                "[href*='publications']",
            ]

            for selector in search_selectors:
                try:
                    link = await page.query_selector(selector)
                    if link:
                        await link.click()
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(2)
                        logger.debug("Navigated to search via %s", selector)
                        return
                except Exception:
                    continue

            # If no link found, the main page might already show results
            logger.debug("Could not find search link, using current page")

        except Exception as e:
            logger.debug("Navigation error: %s", e)

    async def _parse_search_results(self, page) -> List[RawProject]:
        """Parse current page for tender listings."""
        projects = []

        try:
            # Wait for results to load
            await page.wait_for_selector(
                "article, .publication-item, .tender-item, "
                "[class*='publication'], [class*='tender'], .search-result",
                timeout=10000,
            )
        except Exception:
            # Try alternative: look for any list items
            pass

        # Try multiple selector patterns for React-rendered content
        item_selectors = [
            "article",
            "[class*='publication']",
            "[class*='tender']",
            ".search-result",
            "[data-testid*='publication']",
            "tr[class*='row']",
            ".list-item",
        ]

        items = []
        for selector in item_selectors:
            items = await page.query_selector_all(selector)
            if items:
                logger.debug("Found %d items with selector: %s", len(items), selector)
                break

        for item in items:
            try:
                project = await self._parse_item(page, item)
                if project:
                    projects.append(project)
            except Exception:
                continue

        return projects

    async def _parse_item(self, page, item) -> Optional[RawProject]:
        """Parse a single tender item."""
        try:
            # Find link and title
            link = await item.query_selector("a[href]")
            if not link:
                return None

            href = await link.get_attribute("href")
            title = await link.inner_text()

            if not href or not title or len(title.strip()) < 5:
                return None

            title = title.strip()

            # Build full URL
            if not href.startswith("http"):
                href = f"https://www.simap.ch{href}"

            # Extract external ID from URL
            external_id = self._extract_external_id(href)
            if not external_id:
                # Use title hash as fallback
                external_id = f"simap-{hash(title) % 100000000}"

            # Try to extract client name
            client_name = None
            client_selectors = [
                "[class*='authority']",
                "[class*='client']",
                "[class*='organisation']",
                ".vergabestelle",
            ]
            for selector in client_selectors:
                el = await item.query_selector(selector)
                if el:
                    client_name = await el.inner_text()
                    if client_name:
                        break

            # Try to extract deadline
            deadline = None
            deadline_selectors = [
                "time",
                "[class*='deadline']",
                "[class*='date']",
                "[class*='frist']",
            ]
            for selector in deadline_selectors:
                el = await item.query_selector(selector)
                if el:
                    datetime_attr = await el.get_attribute("datetime")
                    if datetime_attr:
                        deadline = self._parse_datetime(datetime_attr)
                    else:
                        text = await el.inner_text()
                        deadline = self._parse_datetime(text)
                    if deadline:
                        break

            # Try to get description snippet
            description = None
            desc_selectors = [
                "[class*='description']",
                "[class*='excerpt']",
                "[class*='summary']",
                "p",
            ]
            for selector in desc_selectors:
                el = await item.query_selector(selector)
                if el:
                    description = await el.inner_text()
                    if description and len(description.strip()) > 20:
                        break

            return RawProject(
                source="simap.ch",
                external_id=external_id,
                url=href,
                title=title,
                client_name=client_name.strip() if client_name else None,
                description=description.strip() if description else None,
                skills=[],
                budget=None,
                location="Schweiz",
                remote=False,
                public_sector=True,
                deadline=deadline,
            )

        except Exception:
            return None

    def _extract_external_id(self, url: str) -> Optional[str]:
        """Extract unique ID from simap.ch URL."""
        patterns = [
            r"projectId=([0-9a-zA-Z_-]+)",
            r"/publication/([0-9a-zA-Z_-]+)",
            r"/project/([0-9a-zA-Z_-]+)",
            r"/([0-9]{5,})",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _parse_datetime(self, text: str) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not text:
            return None

        text = text.strip()

        # ISO format
        iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if iso_match:
            try:
                return datetime(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3)),
                )
            except ValueError:
                pass

        # German/Swiss format (DD.MM.YYYY)
        german_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
        if german_match:
            try:
                return datetime(
                    int(german_match.group(3)),
                    int(german_match.group(2)),
                    int(german_match.group(1)),
                )
            except ValueError:
                pass

        return None

    async def _goto_next_page(self, page) -> bool:
        """Navigate to next page of results."""
        try:
            next_selectors = [
                "button:has-text('Next')",
                "button:has-text('Weiter')",
                "a:has-text('Next')",
                "a:has-text('Weiter')",
                "[aria-label='Next page']",
                "[aria-label='Nächste Seite']",
                ".pagination .next",
                "button[class*='next']",
            ]

            for selector in next_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        is_disabled = await btn.get_attribute("disabled")
                        if is_disabled:
                            continue

                        await btn.click()
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(2)
                        return True
                except Exception:
                    continue

        except Exception:
            pass

        return False


async def run_simap_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run simap.ch scraper standalone.

    Args:
        max_pages: Maximum number of pages to scrape

    Returns:
        List of RawProject objects
    """
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = SimapScraper()
        return await scraper.scrape(max_pages=max_pages)
