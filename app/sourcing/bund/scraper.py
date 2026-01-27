"""Scraper for bund.de (Vergabeplattform des Bundes)."""

import asyncio
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.bund.parser import parse_search_results, parse_detail_page, extract_pdf_links
from app.sourcing.pdf.extractor import (
    download_pdf,
    extract_pdf_text,
    combine_project_text,
    log_large_pdf_warning,
    MAX_PDF_PAGES,
)

logger = get_logger("sourcing.bund")

# Rate limiting constants
DETAIL_PAGE_DELAY_SECONDS = 3.0
PDF_DOWNLOAD_DELAY_SECONDS = 7.0
MAX_PROJECTS_PER_RUN = 20
MAX_PDFS_PER_PROJECT = 3


class BundScraper(BaseScraper):
    """Scraper for bund.de IT service tenders."""

    source_name = "bund.de"

    # Base URL for IT service tenders
    BASE_URL = "https://www.service.bund.de"
    # Updated URL - use the Ausschreibungen Suche with IT filter
    SEARCH_URL = f"{BASE_URL}/Content/DE/Ausschreibungen/Suche/Formular.html"

    # Search parameters for IT services
    SEARCH_PARAMS = {
        "nn": "4641482",
    }

    # Search keywords for IT projects
    SEARCH_KEYWORDS = "Software Entwicklung IT"

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        return True

    async def scrape(self, max_pages: int = 5) -> List[RawProject]:
        """Scrape IT service tenders from bund.de.

        Args:
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []
        search_results = []

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

            # Submit search form to load results
            await self._submit_search_form(page)

            # Try to apply status filter for active tenders only
            await self._apply_status_filter(page)

            # Phase 1: Collect search results from all pages
            for page_num in range(1, max_pages + 1):
                logger.debug("Scraping search page %d...", page_num)

                # Parse search results
                results = await parse_search_results(page)
                if not results:
                    logger.debug("No results on page %d", page_num)
                    break

                logger.debug("Found %d tenders on page %d", len(results), page_num)
                search_results.extend(results)

                # Respect max projects limit
                if len(search_results) >= MAX_PROJECTS_PER_RUN:
                    logger.info("Reached max projects limit (%d)", MAX_PROJECTS_PER_RUN)
                    search_results = search_results[:MAX_PROJECTS_PER_RUN]
                    break

                # Navigate to next page
                if page_num < max_pages:
                    has_next = await self._goto_next_page(page, page_num + 1)
                    if not has_next:
                        break

            # Phase 2: Fetch detail pages and PDFs for each project
            logger.info("Fetching details for %d projects...", len(search_results))

            for i, result in enumerate(search_results):
                # Early filter - skip obviously unsuitable projects
                if should_skip_project(result["title"], result.get("description", "")):
                    logger.debug("Skipping (early filter): %s", result["title"][:50])
                    continue

                logger.debug(
                    "Processing project %d/%d: %s",
                    i + 1,
                    len(search_results),
                    result["title"][:50],
                )

                project = await self._fetch_project_with_pdfs(
                    page,
                    external_id=result["external_id"],
                    url=result["url"],
                    title=result["title"],
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
    ) -> Optional[RawProject]:
        """Fetch project detail page and extract PDFs.

        Args:
            page: Playwright page
            external_id: External project ID
            url: Detail page URL
            title: Project title from search

        Returns:
            RawProject with PDF text, or minimal project on error
        """
        # Rate limiting delay before detail page
        await asyncio.sleep(DETAIL_PAGE_DELAY_SECONDS)

        try:
            # Navigate to detail page
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.scraper_timeout_ms,
            )

            # Parse detail page
            project = await parse_detail_page(page, external_id, url)

            if not project:
                # Fallback to minimal project
                project = RawProject(
                    source="bund.de",
                    external_id=external_id,
                    url=url,
                    title=title,
                    public_sector=True,
                )

            # Use title from search if detail parsing failed
            if not project.title:
                project.title = title

            # Extract PDF links
            pdf_links = await extract_pdf_links(page, max_pdfs=MAX_PDFS_PER_PROJECT)
            logger.debug("Found %d PDF links for %s", len(pdf_links), external_id)

            # Download and extract PDF content
            pdf_texts = []
            pdf_urls = []

            for pdf_info in pdf_links:
                pdf_url = pdf_info["url"]
                pdf_title = pdf_info.get("title", "")

                logger.debug("Downloading PDF: %s", pdf_title[:50] or pdf_url[:50])

                pdf_bytes = await download_pdf(
                    page,
                    pdf_url,
                    delay=PDF_DOWNLOAD_DELAY_SECONDS,
                )

                if pdf_bytes:
                    text, was_truncated = extract_pdf_text(pdf_bytes)

                    if was_truncated:
                        log_large_pdf_warning(
                            project_id=external_id,
                            pdf_url=pdf_url,
                            page_count=100,  # Estimate, actual count logged in extract_pdf_text
                            processed_pages=MAX_PDF_PAGES,
                        )

                    if text:
                        pdf_texts.append(text)
                        pdf_urls.append(pdf_url)
                        logger.info(
                            "Extracted %d chars from PDF: %s",
                            len(text),
                            pdf_title[:50] or pdf_url[:50],
                        )

            # Combine PDF texts with description
            if pdf_texts:
                project.pdf_text = combine_project_text(
                    html_desc=project.description or "",
                    pdf_texts=pdf_texts,
                )
                project.pdf_urls = pdf_urls
                logger.info(
                    "Project %s: %d PDFs, %d total chars",
                    external_id,
                    len(pdf_urls),
                    len(project.pdf_text or ""),
                )

            return project

        except Exception as e:
            logger.warning("Error fetching project %s: %s", external_id, e)

            # Retry once after delay
            await asyncio.sleep(10)
            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=settings.scraper_timeout_ms,
                )
                project = await parse_detail_page(page, external_id, url)
                if project:
                    return project
            except Exception:
                pass

            # Return minimal project as fallback
            return RawProject(
                source="bund.de",
                external_id=external_id,
                url=url,
                title=title,
                public_sector=True,
            )

    def _build_search_url(self, page: int = 1) -> str:
        """Build search URL with parameters."""
        params = [f"{k}={v}" for k, v in self.SEARCH_PARAMS.items()]
        if page > 1:
            params.append(f"page={page}")
        return f"{self.SEARCH_URL}?{'&'.join(params)}"

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent popup if present."""
        try:
            consent_btn = await page.query_selector(
                "button:has-text('Akzeptieren'), "
                "button:has-text('Alle akzeptieren'), "
                ".cookie-consent button"
            )
            if consent_btn:
                await consent_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

    async def _submit_search_form(self, page) -> None:
        """Submit the search form with IT keywords to load results."""
        try:
            # Find search text input and enter IT keywords
            search_input = await page.query_selector(
                "input[type='text'], input[type='search'], "
                "input[name*='search'], input[name*='query']"
            )
            if search_input:
                await search_input.fill(self.SEARCH_KEYWORDS)
                logger.debug("Entered search keywords: %s", self.SEARCH_KEYWORDS)
                await asyncio.sleep(1)

            # The bund.de search form needs to be submitted to show results
            submit_btn = await page.query_selector(
                "button[type='submit'], "
                "input[type='submit'], "
                "button:has-text('Such'), "
                "button:has-text('Anzeigen'), "
                ".btn-primary"
            )
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(3)
        except Exception as e:
            logger.warning("Error submitting search form: %s", e)

    async def _apply_status_filter(self, page) -> bool:
        """Apply filter to show only active tenders (not awarded).

        Tries to find and activate checkboxes/radios for active tenders.

        Returns:
            True if filter was successfully applied
        """
        try:
            # Selectors for active tender filters on bund.de
            # The exact selectors depend on the current bund.de UI
            selectors = [
                # Status filter checkboxes
                'input[name*="status"][value*="ausschreibung"]',
                'input[name*="status"][value*="aktiv"]',
                'input[name*="art"][value*="ausschreibung"]',
                # Checkbox for "nur aktive"
                'input[type="checkbox"][id*="aktiv"]',
                'input[type="checkbox"][name*="nurAktive"]',
                # Radio buttons
                'input[type="radio"][value*="offen"]',
                'input[type="radio"][value*="laufend"]',
            ]

            filter_applied = False
            for sel in selectors:
                element = await page.query_selector(sel)
                if element:
                    is_checked = await element.is_checked()
                    if not is_checked:
                        await element.check()
                        filter_applied = True
                        logger.debug("Applied status filter with selector: %s", sel)
                        break

            if filter_applied:
                # Submit form again after applying filter
                submit_btn = await page.query_selector(
                    'input[type="submit"], button[type="submit"]'
                )
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)

            return filter_applied

        except Exception as e:
            logger.warning("Could not apply status filter: %s", e)
            return False

    async def _goto_next_page(self, page, next_page_num: int) -> bool:
        """Navigate to next results page."""
        try:
            # Try pagination link
            next_link = await page.query_selector(
                f"a[href*='page={next_page_num}'], "
                f"a:has-text('{next_page_num}'), "
                ".pagination .next"
            )
            if next_link:
                await next_link.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(1)
                return True
        except Exception:
            pass

        return False


async def run_bund_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run bund.de scraper.

    Args:
        max_pages: Maximum pages to scrape

    Returns:
        List of scraped projects
    """
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = BundScraper()
        return await scraper.scrape(max_pages=max_pages)
