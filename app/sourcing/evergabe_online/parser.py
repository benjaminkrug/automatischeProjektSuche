"""Parser for evergabe-online.de search results and detail pages."""

import re
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> List[Dict[str, Any]]:
    """Parse search results from evergabe-online.de.

    Args:
        page: Playwright page with loaded search results

    Returns:
        List of dicts with external_id, url, title, client_name, deadline
    """
    results = []

    # evergabe-online.de uses a table with tbody tr for results
    rows = await page.query_selector_all("table tbody tr")

    if not rows:
        return results

    for row in rows[:30]:
        try:
            result = await _parse_table_row(row)
            if result:
                results.append(result)
        except Exception:
            continue

    return results


async def _parse_table_row(row) -> Optional[Dict[str, Any]]:
    """Parse a table row from evergabe-online.de search results.

    Table structure:
    Cell 0: Title (with link to tenderdetails.html?id=...)
    Cell 1: Reference number
    Cell 2: Client/Auftraggeber
    Cell 3: Location
    Cell 4: Procedure type
    Cell 5: Deadline
    Cell 6: Publication date
    """
    cells = await row.query_selector_all("td")
    if len(cells) < 3:
        return None

    # Get title and link from first cell
    link = await cells[0].query_selector("a[href*='tenderdetails']")
    if not link:
        return None

    href = await link.get_attribute("href")
    title = await link.inner_text()

    if not href or not title or len(title.strip()) < 5:
        return None

    title = title.strip()
    url = _normalize_url(href)
    external_id = _generate_id(url)

    # Get client name from cell 2
    client_name = None
    if len(cells) > 2:
        client_name = (await cells[2].inner_text()).strip()

    # Get deadline from cell 5
    deadline = None
    if len(cells) > 5:
        deadline_text = await cells[5].inner_text()
        deadline = _parse_date(deadline_text)

    return {
        "external_id": external_id,
        "url": url,
        "title": title,
        "client_name": client_name,
        "deadline": deadline,
    }


async def _parse_result_item(item) -> Optional[Dict[str, Any]]:
    """Parse a single search result item."""
    # Find title link
    link = await item.query_selector(
        "a.title, a[href*='vergabe'], a[href*='detail'], h3 a, td a"
    )
    if not link:
        link = await item.query_selector("a")

    if not link:
        return None

    href = await link.get_attribute("href")
    title = await link.inner_text()

    if not href or not title or len(title.strip()) < 5:
        return None

    title = title.strip()
    url = _normalize_url(href)
    external_id = _generate_id(url)

    # Extract client
    client_name = None
    for sel in [".auftraggeber", ".client", ".vergabestelle", "td:nth-child(2)"]:
        el = await item.query_selector(sel)
        if el:
            text = await el.inner_text()
            if text and len(text.strip()) > 3:
                client_name = text.strip()
                break

    # Extract deadline
    deadline = None
    for sel in [".deadline", ".frist", ".date", "td:nth-child(3)"]:
        el = await item.query_selector(sel)
        if el:
            text = await el.inner_text()
            deadline = _parse_date(text)
            if deadline:
                break

    return {
        "external_id": external_id,
        "url": url,
        "title": title,
        "client_name": client_name,
        "deadline": deadline,
    }


async def parse_detail_page(page: Page, external_id: str, url: str) -> Optional[RawProject]:
    """Parse tender detail page.

    Args:
        page: Playwright page with loaded detail
        external_id: External ID
        url: Detail page URL

    Returns:
        RawProject or None
    """
    # Extract title
    title = None
    for sel in ["h1", ".tender-title", ".bekanntmachung-titel", "h2.title"]:
        el = await page.query_selector(sel)
        if el:
            title = (await el.inner_text()).strip()
            if title and len(title) > 5:
                break

    if not title:
        return None

    # Extract description
    description = None
    for sel in [".description", ".leistungsbeschreibung", ".content", ".detail-text"]:
        el = await page.query_selector(sel)
        if el:
            description = (await el.inner_text()).strip()
            if description:
                break

    # Extract client
    client_name = None
    for sel in [".auftraggeber", ".vergabestelle", ".client"]:
        el = await page.query_selector(sel)
        if el:
            text = await el.inner_text()
            # Clean label if present
            client_name = re.sub(r"^(Auftraggeber|Vergabestelle)[:\s]*", "", text).strip()
            if client_name:
                break

    # Extract deadline
    deadline = None
    for sel in [".deadline", ".frist", ".abgabetermin"]:
        el = await page.query_selector(sel)
        if el:
            text = await el.inner_text()
            deadline = _parse_date(text)
            if deadline:
                break

    # Extract location
    location = None
    for sel in [".location", ".ort", ".erfuellungsort"]:
        el = await page.query_selector(sel)
        if el:
            location = (await el.inner_text()).strip()
            if location:
                break

    # Check remote
    full_text = f"{title} {description or ''} {location or ''}".lower()
    remote = any(kw in full_text for kw in ["remote", "homeoffice", "home-office"])

    return RawProject(
        source="evergabe_online",
        external_id=external_id,
        url=url,
        title=title,
        client_name=client_name,
        description=description,
        location=location,
        remote=remote,
        public_sector=True,
        deadline=deadline,
    )


async def extract_pdf_links(page: Page, max_pdfs: int = 3) -> List[Dict[str, str]]:
    """Extract PDF download links.

    Filters out known non-PDF links like installer downloads.
    """
    pdf_links = []

    # Paths that look like downloads but are not actual tender PDFs
    EXCLUDED_PATH_PATTERNS = [
        "/downloads/installer/",
        "/downloads/software/",
        "/downloads/client/",
        "evergabeapp",
        "signatureclient",
        "viewer",
        "plugin",
    ]

    links = await page.query_selector_all(
        "a[href*='.pdf'], a[href*='download'], a.document-link"
    )

    for link in links[:max_pdfs * 3]:
        try:
            href = await link.get_attribute("href")
            if not href:
                continue

            href_lower = href.lower()

            # Skip excluded patterns (installers, clients, etc.)
            if any(pattern in href_lower for pattern in EXCLUDED_PATH_PATTERNS):
                continue

            # Must have .pdf extension OR be a document download (not installer)
            is_pdf_extension = ".pdf" in href_lower
            is_document_download = (
                "download" in href_lower
                and "/document" in href_lower
            )

            if not is_pdf_extension and not is_document_download:
                continue

            title = await link.inner_text()
            title = title.strip() if title else "Dokument"

            pdf_links.append({
                "url": _normalize_url(href),
                "title": title,
            })

            if len(pdf_links) >= max_pdfs:
                break

        except Exception:
            continue

    return pdf_links


def _generate_id(url: str) -> str:
    """Generate unique ID from URL."""
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _normalize_url(url: str) -> str:
    """Normalize URL."""
    if url.startswith("./"):
        return f"https://www.evergabe-online.de/{url[2:]}"
    if url.startswith("/"):
        return f"https://www.evergabe-online.de{url}"
    if not url.startswith("http"):
        return f"https://www.evergabe-online.de/{url}"
    return url


def _parse_date(text: str) -> Optional[datetime]:
    """Parse date from text."""
    if not text:
        return None

    patterns = [
        r"(\d{1,2})[./](\d{1,2})[./](\d{4})",
        r"(\d{4})-(\d{2})-(\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                groups = match.groups()
                if len(groups[0]) == 4:
                    return datetime(int(groups[0]), int(groups[1]), int(groups[2]))
                else:
                    return datetime(int(groups[2]), int(groups[1]), int(groups[0]))
            except ValueError:
                continue

    return None
