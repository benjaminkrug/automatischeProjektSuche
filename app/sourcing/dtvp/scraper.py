"""Scraper for DTVP (Deutsches Vergabeportal) - German public procurement."""

import asyncio
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.dtvp.parser import parse_search_results, parse_detail_page

logger = get_logger("sourcing.dtvp")


class DtvpScraper(BaseScraper):
    """Scraper for DTVP German public procurement tenders.

    DTVP (Deutsches Vergabeportal) hosts tenders from over 5,000 German
    contracting authorities. This scraper targets IT services using
    multiple CPV codes for software and IT services.
    """

    source_name = "dtvp"

    # Base search URL for category overview
    BASE_SEARCH_URL = (
        "https://www.dtvp.de/Center/company/announcements/categoryOverview.do"
    )

    # IT-relevant CPV codes with their categories
    CPV_CODES = [
        "72200000-7",  # Softwareprogrammierung
        "72400000-4",  # Internetdienste
        "72300000-8",  # Datendienste
    ]

    # Publication type filter: only open tenders
    PUBLICATION_TYPE_FILTER = "Tender"  # Options: Tender, ExAnte, ExPost

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        """DTVP is always public sector."""
        return True

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape IT tenders from DTVP across multiple CPV categories.

        Args:
            max_pages: Maximum number of result pages to scrape per category

        Returns:
            List of RawProject objects
        """
        projects = []
        seen_ids = set()

        async with self._browser_manager.page_context() as page:
            for cpv_code in self.CPV_CODES:
                search_url = self._build_search_url(cpv_code)
                logger.info("Scraping CPV %s: %s", cpv_code, search_url)

                try:
                    await page.goto(
                        search_url,
                        wait_until="domcontentloaded",
                        timeout=settings.scraper_timeout_ms,
                    )
                except Exception as e:
                    logger.error("Error loading search page for CPV %s: %s", cpv_code, e)
                    continue

                # Handle cookie consent (only needed on first load)
                if cpv_code == self.CPV_CODES[0]:
                    await self._handle_cookie_consent(page)

                # Wait for dynamic content to load
                await asyncio.sleep(2)

                # Apply publication type filter (only open tenders)
                filtered = await self._apply_publication_filter(page)
                if not filtered:
                    logger.warning("Could not apply filter for CPV %s", cpv_code)

                for page_num in range(1, max_pages + 1):
                    logger.debug("Scraping CPV %s page %d...", cpv_code, page_num)

                    results = await parse_search_results(page)
                    if not results:
                        logger.debug("No results on page %d for CPV %s", page_num, cpv_code)
                        break

                    logger.debug("Found %d tenders on page %d", len(results), page_num)

                    for result in results:
                        # Deduplicate across CPV categories
                        if result["external_id"] in seen_ids:
                            continue
                        seen_ids.add(result["external_id"])

                        project = await self._get_tender_details(
                            page,
                            result["external_id"],
                            result["url"],
                            result["title"],
                            result.get("client_name"),
                            result.get("deadline_text"),
                        )
                        if project:
                            projects.append(project)

                        await asyncio.sleep(settings.scraper_delay_seconds)

                    if page_num < max_pages:
                        has_next = await self._goto_next_page(page)
                        if not has_next:
                            break

        logger.info("Total scraped: %d unique tenders", len(projects))
        return projects

    def _build_search_url(self, cpv_code: str) -> str:
        """Build search URL for a specific CPV code.

        Args:
            cpv_code: CPV code to search for (e.g. '72200000-7')

        Returns:
            Full search URL
        """
        return f"{self.BASE_SEARCH_URL}?method=showTable&cpvCode={cpv_code}"

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup if present."""
        try:
            # Common German cookie consent button selectors
            consent_selectors = [
                "button:has-text('Akzeptieren')",
                "button:has-text('Alle akzeptieren')",
                "button:has-text('Einverstanden')",
                "button:has-text('Zustimmen')",
                ".cookie-consent-accept",
                "#cookie-accept",
                "[data-cookie-accept]",
                "button[class*='accept']",
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

    async def _apply_publication_filter(self, page) -> bool:
        """Apply publication type filter to show only open tenders.

        DTVP requires clicking a checkbox and submitting the filter form.
        Filter options: Tender (open), ExAnte (planned), ExPost (awarded)

        Args:
            page: Playwright page instance

        Returns:
            True if filter was applied successfully
        """
        try:
            # Check the publication type checkbox
            filter_value = self.PUBLICATION_TYPE_FILTER
            checkbox_selector = f'input[name="selectedPublicationTypes"][value="{filter_value}"]'

            checkbox = await page.query_selector(checkbox_selector)
            if not checkbox:
                logger.debug("Publication filter checkbox not found")
                return False

            # Check if already checked
            is_checked = await checkbox.is_checked()
            if not is_checked:
                await checkbox.check()
                logger.debug("Checked %s filter", filter_value)

            # Click the "Filtern" button to apply
            filter_button = await page.query_selector('input[value="Filtern"]')
            if filter_button:
                await filter_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1)
                logger.debug("Applied publication filter: %s", filter_value)
                return True

            logger.debug("Filter button not found")
            return False

        except Exception as e:
            logger.warning("Error applying publication filter: %s", e)
            return False

    async def _get_tender_details(
        self,
        page,
        external_id: str,
        url: str,
        title: str,
        client_name: Optional[str] = None,
        deadline_text: Optional[str] = None,
    ) -> Optional[RawProject]:
        """Navigate to tender detail page and extract info.

        Args:
            page: Playwright page instance
            external_id: Unique tender identifier
            url: URL to the detail page
            title: Tender title from search results
            client_name: Client name from search results (fallback)
            deadline_text: Deadline text from search results (fallback)

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
                # Check for login page redirect (secured URLs require auth)
                login_indicators = [
                    "Anmeldung für Unternehmen",
                    "Anmeldung fur Unternehmen",
                    "Login",
                ]
                if any(indicator in project.title for indicator in login_indicators):
                    # Use fallback with search results data
                    return self._create_fallback_project(
                        external_id, url, title, client_name, deadline_text
                    )

                # Fill in missing data from search results
                if not project.title or project.title.startswith("Ausschreibung"):
                    project.title = title
                if not project.client_name and client_name:
                    project.client_name = client_name
                # Use search results deadline if detail page didn't have one
                if not project.deadline and deadline_text:
                    from app.sourcing.dtvp.parser import _parse_datetime
                    project.deadline = _parse_datetime(deadline_text)

                return project

            # Fallback if detail parsing fails
            return self._create_fallback_project(
                external_id, url, title, client_name, deadline_text
            )

        except Exception as e:
            logger.warning("Error getting details for %s: %s", external_id, e)
            return self._create_fallback_project(
                external_id, url, title, client_name, deadline_text
            )

    def _create_fallback_project(
        self,
        external_id: str,
        url: str,
        title: str,
        client_name: Optional[str] = None,
        deadline_text: Optional[str] = None,
    ) -> RawProject:
        """Create a fallback RawProject with minimal data.

        Args:
            external_id: Unique tender identifier
            url: URL to the detail page
            title: Tender title
            client_name: Client name if available
            deadline_text: Deadline text if available

        Returns:
            RawProject with available data
        """
        from app.sourcing.dtvp.parser import _parse_datetime

        deadline = _parse_datetime(deadline_text) if deadline_text else None

        return RawProject(
            source="dtvp",
            external_id=external_id,
            url=url,
            title=title,
            client_name=client_name,
            public_sector=True,
            deadline=deadline,
        )

    async def _goto_next_page(self, page) -> bool:
        """Navigate to the next results page via JavaScript click.

        DTVP uses JavaScript-based pagination with arrow icons instead of
        URL-based pagination.

        Args:
            page: Playwright page instance

        Returns:
            True if navigation succeeded, False otherwise
        """
        try:
            # DTVP-specific navigation selectors (arrow icons and German labels)
            next_selectors = [
                "img[src*='arrow_right']",
                "img[src*='next']",
                "a[title*='chste']",  # 'naechste' (next)
                "a[title*='weiter']",
                "a:has-text('>')",
                "a:has-text('>>')",
                ".pagination-next",
                "a.next:not(.disabled)",
                "a[aria-label='Nächste Seite']",
                ".pager-next a",
                "input[value='>']",
                "button:has-text('Weiter')",
            ]

            for selector in next_selectors:
                try:
                    next_btn = await page.query_selector(selector)
                    if next_btn:
                        # Check if disabled
                        is_disabled = await next_btn.get_attribute("disabled")
                        aria_disabled = await next_btn.get_attribute("aria-disabled")
                        class_attr = await next_btn.get_attribute("class") or ""

                        if is_disabled or aria_disabled == "true" or "disabled" in class_attr:
                            continue

                        await next_btn.click()
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(1)
                        return True
                except Exception:
                    continue

        except Exception:
            pass

        return False


async def run_dtvp_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run DTVP scraper standalone.

    Args:
        max_pages: Maximum number of pages to scrape

    Returns:
        List of RawProject objects
    """
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = DtvpScraper()
        return await scraper.scrape(max_pages=max_pages)
