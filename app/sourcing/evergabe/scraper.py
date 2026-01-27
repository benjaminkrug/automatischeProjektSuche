"""Scraper for evergabe.de (German public procurement aggregator)."""

import asyncio
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.evergabe.parser import (
    parse_search_results,
    parse_detail_page,
    extract_pdf_links,
)
from app.sourcing.pdf.extractor import (
    download_pdf,
    extract_pdf_text,
    combine_project_text,
    MAX_PDF_PAGES,
)

logger = get_logger("sourcing.evergabe")

# Rate limiting
DETAIL_PAGE_DELAY_SECONDS = 2.0
PDF_DOWNLOAD_DELAY_SECONDS = 5.0
MAX_PROJECTS_PER_RUN = 25
MAX_PDFS_PER_PROJECT = 2

# CPV code for IT services
CPV_IT_SERVICES = "72000000"


class EvergabeScraper(BaseScraper):
    """Scraper for evergabe.de public procurement aggregator.

    evergabe.de aggregates tenders from multiple German public
    procurement platforms. It provides a unified search interface
    for IT service tenders.
    """

    source_name = "evergabe"

    BASE_URL = "https://www.evergabe.de"
    SEARCH_URL = f"{BASE_URL}/auftraege/auftrag-suchen"

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        return True

    async def scrape(self, max_pages: int = 3) -> List[RawProject]:
        """Scrape IT tenders from evergabe.de.

        Args:
            max_pages: Maximum result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []
        search_results = []

        async with self._browser_manager.page_context() as page:
            # Navigate to search page
            logger.info("Navigating to %s", self.SEARCH_URL)

            try:
                await page.goto(
                    self.SEARCH_URL,
                    wait_until="domcontentloaded",
                    timeout=settings.scraper_timeout_ms,
                )
            except Exception as e:
                logger.error("Error loading search page: %s", e)
                return projects

            # Handle cookie consent
            await self._handle_cookie_consent(page)

            # Apply IT filter (CPV code 72000000)
            await self._apply_it_filter(page)

            # Collect search results
            for page_num in range(1, max_pages + 1):
                logger.debug("Scraping page %d...", page_num)

                results = await parse_search_results(page)
                if not results:
                    logger.debug("No results on page %d", page_num)
                    break

                logger.debug("Found %d tenders on page %d", len(results), page_num)
                search_results.extend(results)

                if len(search_results) >= MAX_PROJECTS_PER_RUN:
                    search_results = search_results[:MAX_PROJECTS_PER_RUN]
                    break

                # Navigate to next page
                if page_num < max_pages:
                    has_next = await self._goto_next_page(page)
                    if not has_next:
                        break

            # Fetch detail pages
            logger.info("Fetching details for %d projects...", len(search_results))

            for i, result in enumerate(search_results):
                # Early filter
                if should_skip_project(result["title"], ""):
                    logger.debug("Skipping (early filter): %s", result["title"][:50])
                    continue

                logger.debug(
                    "Processing %d/%d: %s",
                    i + 1,
                    len(search_results),
                    result["title"][:50],
                )

                project = await self._fetch_project_with_pdfs(
                    page,
                    external_id=result["external_id"],
                    url=result["url"],
                    title=result["title"],
                    client_name=result.get("client_name"),
                    deadline=result.get("deadline"),
                )

                if project:
                    projects.append(project)

        logger.info("Total scraped: %d projects", len(projects))
        return projects

    async def _fetch_project_with_pdfs(
        self,
        page,
        external_id: str,
        url: str,
        title: str,
        client_name: Optional[str] = None,
        deadline=None,
    ) -> Optional[RawProject]:
        """Fetch project detail page and PDFs."""
        await asyncio.sleep(DETAIL_PAGE_DELAY_SECONDS)

        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )

            project = await parse_detail_page(page, external_id, url)

            if not project:
                project = RawProject(
                    source="evergabe",
                    external_id=external_id,
                    url=url,
                    title=title,
                    client_name=client_name,
                    public_sector=True,
                    deadline=deadline,
                )

            # Use search data as fallback
            if not project.title:
                project.title = title
            if not project.client_name and client_name:
                project.client_name = client_name
            if not project.deadline and deadline:
                project.deadline = deadline

            # Extract PDFs
            pdf_links = await extract_pdf_links(page, max_pdfs=MAX_PDFS_PER_PROJECT)
            logger.debug("Found %d PDF links", len(pdf_links))

            pdf_texts = []
            pdf_urls = []

            for pdf_info in pdf_links:
                pdf_url = pdf_info["url"]
                pdf_title = pdf_info.get("title", "")

                logger.debug("Downloading PDF: %s", pdf_title[:40] or pdf_url[:40])

                pdf_bytes = await download_pdf(
                    page,
                    pdf_url,
                    delay=PDF_DOWNLOAD_DELAY_SECONDS,
                )

                if pdf_bytes:
                    text, _ = extract_pdf_text(pdf_bytes)
                    if text:
                        pdf_texts.append(text)
                        pdf_urls.append(pdf_url)

            if pdf_texts:
                project.pdf_text = combine_project_text(
                    html_desc=project.description or "",
                    pdf_texts=pdf_texts,
                )
                project.pdf_urls = pdf_urls

            return project

        except Exception as e:
            logger.warning("Error fetching project %s: %s", external_id, e)
            return RawProject(
                source="evergabe",
                external_id=external_id,
                url=url,
                title=title,
                client_name=client_name,
                public_sector=True,
                deadline=deadline,
            )

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup."""
        try:
            consent_selectors = [
                "button:has-text('Akzeptieren')",
                "button:has-text('Alle akzeptieren')",
                "button:has-text('Accept')",
                ".cookie-consent button",
                "#cookie-accept",
            ]
            for sel in consent_selectors:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
                    break
        except Exception:
            pass

    async def _apply_it_filter(self, page) -> None:
        """Apply CPV filter for IT services."""
        try:
            # Try to find CPV input field
            cpv_selectors = [
                "input[name*='cpv']",
                "input[placeholder*='CPV']",
                "#cpv-filter",
                ".cpv-input",
            ]

            for sel in cpv_selectors:
                input_el = await page.query_selector(sel)
                if input_el:
                    await input_el.fill(CPV_IT_SERVICES)
                    await asyncio.sleep(0.5)
                    break

            # Try keyword search as fallback
            search_selectors = [
                "input[type='search']",
                "input[name*='search']",
                "input[name*='query']",
                "#search-input",
            ]

            for sel in search_selectors:
                input_el = await page.query_selector(sel)
                if input_el:
                    await input_el.fill("IT Software Entwicklung")
                    await asyncio.sleep(0.5)
                    break

            # Submit search
            submit_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                ".search-button",
                "button:has-text('Suchen')",
            ]

            for sel in submit_selectors:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(2)
                    break

        except Exception as e:
            logger.warning("Could not apply IT filter: %s", e)

    async def _goto_next_page(self, page) -> bool:
        """Navigate to next results page."""
        try:
            next_selectors = [
                ".pagination .next",
                "a:has-text('Weiter')",
                "a:has-text('>')",
                ".next-page",
                "[aria-label='Next']",
            ]

            for sel in next_selectors:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(1.5)
                    return True

        except Exception:
            pass

        return False


async def run_evergabe_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run evergabe.de scraper."""
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = EvergabeScraper()
        return await scraper.scrape(max_pages=max_pages)
