"""Scraper for evergabe-online.de (German public procurement platform)."""

import asyncio
from typing import List, Optional

from app.core.logging import get_logger
from app.settings import settings
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.playwright.browser import get_browser_manager
from app.sourcing.evergabe_online.parser import (
    parse_search_results,
    parse_detail_page,
    extract_pdf_links,
)
from app.sourcing.pdf.extractor import (
    download_pdf,
    extract_pdf_text,
    combine_project_text,
)

logger = get_logger("sourcing.evergabe_online")

# Rate limiting
DETAIL_PAGE_DELAY_SECONDS = 2.5
PDF_DOWNLOAD_DELAY_SECONDS = 5.0
MAX_PROJECTS_PER_RUN = 20
MAX_PDFS_PER_PROJECT = 2


class EvergabeOnlineScraper(BaseScraper):
    """Scraper for evergabe-online.de.

    evergabe-online.de is a German public procurement platform
    used by 600+ public sector organizations. Provides public
    search without login requirement.
    """

    source_name = "evergabe_online"

    BASE_URL = "https://www.evergabe-online.de"
    SEARCH_URL = f"{BASE_URL}/search.html"

    def __init__(self):
        self._browser_manager = get_browser_manager()

    def is_public_sector(self) -> bool:
        return True

    async def scrape(self, max_pages: int = 3) -> List[RawProject]:
        """Scrape IT tenders from evergabe-online.de.

        Args:
            max_pages: Maximum result pages to scrape

        Returns:
            List of RawProject objects
        """
        projects = []
        search_results = []

        async with self._browser_manager.page_context() as page:
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

            # Apply IT filter
            await self._apply_search_filter(page)

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

                if page_num < max_pages:
                    has_next = await self._goto_next_page(page)
                    if not has_next:
                        break

            # Fetch details
            logger.info("Fetching details for %d projects...", len(search_results))

            for i, result in enumerate(search_results):
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
        """Fetch project detail and PDFs."""
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
                    source="evergabe_online",
                    external_id=external_id,
                    url=url,
                    title=title,
                    client_name=client_name,
                    public_sector=True,
                    deadline=deadline,
                )

            # Always prefer title from search results (detail page may have generic title)
            if title and len(title) > 5:
                project.title = title
            if not project.client_name and client_name:
                project.client_name = client_name
            if not project.deadline and deadline:
                project.deadline = deadline

            # PDFs
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
                source="evergabe_online",
                external_id=external_id,
                url=url,
                title=title,
                client_name=client_name,
                public_sector=True,
                deadline=deadline,
            )

    async def _handle_cookie_consent(self, page) -> None:
        """Handle cookie consent."""
        try:
            for sel in [
                "button:has-text('Akzeptieren')",
                "button:has-text('Alle akzeptieren')",
                ".cookie-consent button",
                "#accept-cookies",
            ]:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
                    break
        except Exception:
            pass

    async def _apply_search_filter(self, page) -> None:
        """Apply IT keyword filter.

        This is best-effort - if elements are not found, we continue
        with unfiltered results rather than timing out.
        """
        search_applied = False

        try:
            # Find search input (quick check, no waiting)
            input_el = None
            for sel in [
                "input[type='search']",
                "input[name*='search']",
                "input[name*='suchbegriff']",
                "#searchInput",
            ]:
                input_el = await page.query_selector(sel)
                if input_el and await input_el.is_visible():
                    await input_el.fill("IT Software Entwicklung")
                    await asyncio.sleep(0.5)
                    search_applied = True
                    break

            # Category filter if available (optional)
            for sel in [
                "select[name*='kategorie']",
                "select[name*='category']",
                "#category-select",
            ]:
                select = await page.query_selector(sel)
                if select and await select.is_visible():
                    try:
                        await select.select_option(label="IT/EDV")
                        await asyncio.sleep(0.5)
                    except Exception:
                        # Option might not exist
                        pass
                    break

            # Only submit if we applied a search filter
            if search_applied:
                for sel in [
                    "button[type='submit']",
                    "input[type='submit']",
                    "button:has-text('Suchen')",
                    ".search-submit",
                ]:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await asyncio.sleep(2)
                        break

            if not search_applied:
                logger.debug("No search filter applied - using default results")

        except Exception as e:
            logger.warning("Could not apply search filter: %s", e)

    async def _goto_next_page(self, page) -> bool:
        """Navigate to next page."""
        try:
            for sel in [
                ".pagination .next",
                "a:has-text('Weiter')",
                "a:has-text('>')",
                ".next-page",
            ]:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(1.5)
                    return True
        except Exception:
            pass
        return False


async def run_evergabe_online_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run evergabe-online.de scraper."""
    from app.sourcing.playwright.browser import browser_session

    async with browser_session():
        scraper = EvergabeOnlineScraper()
        return await scraper.scrape(max_pages=max_pages)
