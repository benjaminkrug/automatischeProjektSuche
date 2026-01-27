"""Scraper for Vergabe24 - German public procurement portal."""

import asyncio
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.vergabe24.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.vergabe24")


class Vergabe24Scraper(BaseScraper):
    """Scraper for Vergabe24 German public procurement tenders.

    Vergabe24 is a German public procurement aggregator built on WordPress.
    It aggregates tenders from various German contracting authorities.
    """

    source_name = "vergabe24"

    # Main landing page with tender carousel
    MAIN_URL = "https://www.vergabe24.de/auftragnehmer/suche-nach-ausschreibungen/"
    # Direct search URL pattern
    SEARCH_URL = "https://www.vergabe24.de/"
    CPV_IT = "72000000"

    def __init__(self):
        """Initialize the Vergabe24 scraper."""
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        """Vergabe24 is always public sector."""
        return True

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape IT tenders from Vergabe24.

        Args:
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []

        async with self._browser_manager.page_context() as page:
            # Try the main page first (has carousel with latest tenders)
            logger.debug("Navigating to %s", self.MAIN_URL)

            try:
                await page.goto(
                    self.MAIN_URL,
                    wait_until="networkidle",
                    timeout=settings.scraper_timeout_ms,
                )
            except Exception as e:
                logger.error("Error loading main page: %s", e)
                return projects

            # Handle cookie consent
            await self._handle_cookie_consent(page)

            # Wait for dynamic content (Splide carousel)
            await asyncio.sleep(3)

            # First, try to scrape from the carousel on main page
            logger.debug("Scraping carousel items...")
            carousel_results = await self._parse_carousel(page)
            if carousel_results:
                logger.debug("Found %d items in carousel", len(carousel_results))
                for result in carousel_results:
                    project = await self._get_tender_details(
                        page,
                        result["external_id"],
                        result["url"],
                        result["title"],
                        result.get("client_name"),
                        result.get("deadline_text"),
                        result.get("excerpt"),
                    )
                    if project:
                        projects.append(project)
                    await asyncio.sleep(settings.scraper_delay_seconds)

            # Then try to use search form or pagination
            for page_num in range(1, max_pages + 1):
                logger.debug("Scraping page %d...", page_num)

                results = await parse_search_results(page)
                # Filter out duplicates
                new_results = [r for r in results if r["external_id"] not in
                              {p.external_id for p in projects}]

                if not new_results:
                    logger.debug("No new results on page %d", page_num)
                    break

                logger.debug("Found %d new tenders on page %d", len(new_results), page_num)

                for result in new_results:
                    project = await self._get_tender_details(
                        page,
                        result["external_id"],
                        result["url"],
                        result["title"],
                        result.get("client_name"),
                        result.get("deadline_text"),
                        result.get("excerpt"),
                    )
                    if project:
                        projects.append(project)

                    await asyncio.sleep(settings.scraper_delay_seconds)

                if page_num < max_pages:
                    has_next = await self._goto_next_page(page)
                    if not has_next:
                        break

        logger.info("Total scraped: %d tenders", len(projects))
        return projects

    async def _parse_carousel(self, page) -> List[dict]:
        """Parse the Splide carousel for tender items.

        Args:
            page: Playwright page instance

        Returns:
            List of tender dicts
        """
        results = []

        try:
            # Wait for Splide carousel to load
            await page.wait_for_selector(
                ".splide, .slider-teaser--big, .teaser-card-big",
                timeout=10000
            )
        except Exception:
            return results

        # Get all carousel items
        items = await page.query_selector_all(
            ".teaser-card-big, .splide__slide .teaser-card, "
            ".slider-teaser--big .teaser-card"
        )

        for item in items:
            try:
                # Get link
                link = await item.query_selector("a[href]")
                if not link:
                    continue

                href = await link.get_attribute("href")
                if not href:
                    continue

                # Get title
                title_el = await item.query_selector(
                    ".teaser-card-big__heading, .teaser-card__heading, h2, h3"
                )
                title = await title_el.inner_text() if title_el else await link.inner_text()

                if not title or len(title.strip()) < 10:
                    continue

                # Build full URL
                if not href.startswith("http"):
                    href = f"https://www.vergabe24.de{href}"

                # Extract ID
                external_id = self._extract_carousel_id(href, title)
                if not external_id:
                    continue

                # Get meta info (client, etc.)
                client_name = None
                meta_el = await item.query_selector(
                    ".teaser-card-big__meta, .teaser-card__meta"
                )
                if meta_el:
                    client_name = await meta_el.inner_text()

                results.append({
                    "external_id": external_id,
                    "title": title.strip(),
                    "url": href,
                    "client_name": client_name.strip() if client_name else None,
                    "deadline_text": None,
                    "excerpt": None,
                })

            except Exception:
                continue

        return results

    def _extract_carousel_id(self, url: str, title: str) -> Optional[str]:
        """Extract ID from carousel item URL or generate from title."""
        import re

        # Try URL patterns
        patterns = [
            r"/ausschreibung[/-]([0-9a-zA-Z_-]+)",
            r"/([0-9]{5,})",
            r"[?&]id=([0-9a-zA-Z_-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)

        # Generate from URL path
        path = url.split("?")[0].rstrip("/")
        if "/" in path:
            slug = path.split("/")[-1]
            if slug and len(slug) >= 5:
                return f"v24-{slug[:50]}"

        # Last resort: hash of title
        return f"v24-{abs(hash(title)) % 100000000}"

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup if present."""
        try:
            consent_selectors = [
                "button:has-text('Akzeptieren')",
                "button:has-text('Alle akzeptieren')",
                "button:has-text('Einverstanden')",
                "button:has-text('Zustimmen')",
                ".cookie-consent-accept",
                "#cookie-accept",
                "[data-cookie-accept]",
                "button[class*='accept']",
                ".cmplz-accept",  # Complianz plugin
                "#cmplz-btn-accept",
            ]

            for selector in consent_selectors:
                try:
                    consent_btn = await page.query_selector(selector)
                    if consent_btn:
                        await consent_btn.click()
                        await asyncio.sleep(1)
                        logger.debug("Clicked cookie consent button")
                        return
                except Exception:
                    continue

        except Exception:
            pass

    async def _get_tender_details(
        self,
        page,
        external_id: str,
        url: str,
        title: str,
        client_name: Optional[str] = None,
        deadline_text: Optional[str] = None,
        excerpt: Optional[str] = None,
    ) -> Optional[RawProject]:
        """Navigate to tender detail page and extract info.

        Args:
            page: Playwright page instance
            external_id: Unique tender identifier
            url: URL to the detail page
            title: Tender title from search results
            client_name: Client name from search results (fallback)
            deadline_text: Deadline text from search results (fallback)
            excerpt: Description excerpt from search results (fallback)

        Returns:
            RawProject with extracted data, or fallback project on error
        """
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )

            await asyncio.sleep(1)
            project = await parse_detail_page(page, external_id, url)

            if project:
                # Fill in missing data from search results
                if not project.title or project.title.startswith("Ausschreibung"):
                    project.title = title
                if not project.client_name and client_name:
                    project.client_name = client_name
                if not project.description and excerpt:
                    project.description = excerpt

                return project

            # Fallback if detail parsing fails
            return self._create_fallback_project(
                external_id, url, title, client_name, deadline_text, excerpt
            )

        except Exception as e:
            logger.warning("Error getting details for %s: %s", external_id, e)
            return self._create_fallback_project(
                external_id, url, title, client_name, deadline_text, excerpt
            )

    def _create_fallback_project(
        self,
        external_id: str,
        url: str,
        title: str,
        client_name: Optional[str] = None,
        deadline_text: Optional[str] = None,
        excerpt: Optional[str] = None,
    ) -> RawProject:
        """Create a fallback RawProject with minimal data.

        Args:
            external_id: Unique tender identifier
            url: URL to the detail page
            title: Tender title
            client_name: Client name if available
            deadline_text: Deadline text if available
            excerpt: Description excerpt if available

        Returns:
            RawProject with available data
        """
        from app.sourcing.vergabe24.parser import _parse_datetime

        deadline = _parse_datetime(deadline_text) if deadline_text else None

        return RawProject(
            source="vergabe24",
            external_id=external_id,
            url=url,
            title=title,
            client_name=client_name,
            description=excerpt,
            public_sector=True,
            deadline=deadline,
        )

    async def _goto_next_page(self, page) -> bool:
        """Navigate to the next results page.

        Args:
            page: Playwright page instance

        Returns:
            True if navigation succeeded, False otherwise
        """
        try:
            next_selectors = [
                "a.next:not(.disabled)",
                "a[aria-label='Nächste Seite']",
                "a[aria-label='Next']",
                ".pagination .next a",
                "a:has-text('Weiter')",
                "a:has-text('»')",
                "a:has-text('>')",
                ".nav-links .next",
                "a.next.page-numbers",
            ]

            for selector in next_selectors:
                try:
                    next_link = await page.query_selector(selector)
                    if next_link:
                        is_disabled = await next_link.get_attribute("disabled")
                        aria_disabled = await next_link.get_attribute("aria-disabled")

                        if is_disabled or aria_disabled == "true":
                            continue

                        await next_link.click()
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(2)
                        return True
                except Exception:
                    continue

        except Exception:
            pass

        return False


async def run_vergabe24_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run Vergabe24 scraper standalone.

    Args:
        max_pages: Maximum number of pages to scrape

    Returns:
        List of RawProject objects
    """
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = Vergabe24Scraper()
        return await scraper.scrape(max_pages=max_pages)
