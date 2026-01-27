"""Parser for evergabe.de search results and detail pages."""

import re
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> List[Dict[str, Any]]:
    """Parse search results from evergabe.de.

    Args:
        page: Playwright page with loaded search results

    Returns:
        List of dicts with external_id, url, title, client_name, deadline
    """
    results = []

    # evergabe.de uses result cards with class tw:result-card-grid
    items = await page.query_selector_all('div[class*="result-card"]')

    if not items:
        # Fallback: try generic result divs
        items = await page.query_selector_all('div[class*="result"]')

    if not items:
        # Last resort: find links to /ausschreibung/
        links = await page.query_selector_all("a[href*='/ausschreibung/']")
        for link in links[:30]:
            href = await link.get_attribute("href")
            text = await link.inner_text()
            if href and text and len(text.strip()) > 10 and "/anmelden" not in href:
                results.append({
                    "external_id": _generate_id(href),
                    "url": _normalize_url(href),
                    "title": text.strip(),
                    "client_name": None,
                    "deadline": None,
                })
        return results

    for item in items[:30]:
        try:
            result = await _parse_result_item(item)
            if result:
                results.append(result)
        except Exception:
            continue

    return results


async def _parse_result_item(item) -> Optional[Dict[str, Any]]:
    """Parse a single search result item."""
    # evergabe.de: Find link to /ausschreibung/
    link = await item.query_selector("a[href*='/ausschreibung/']")
    if not link:
        # Fallback selectors
        link = await item.query_selector("a.title, h3 a, h4 a, .title a")
    if not link:
        link = await item.query_selector("a")

    if not link:
        return None

    href = await link.get_attribute("href")
    title = await link.inner_text()

    # Skip login links
    if not href or "/anmelden" in href:
        return None
    if not title or len(title.strip()) < 5:
        return None

    title = title.strip()
    url = _normalize_url(href)
    external_id = _generate_id(url)

    # Try to extract client name from full text
    client_name = None
    full_text = await item.inner_text()
    # Look for "Vergabestelle:" or similar patterns
    if "Vergabestelle" in full_text or "Auftraggeber" in full_text:
        import re
        match = re.search(r"(?:Vergabestelle|Auftraggeber)[:\s]+([^\n]+)", full_text)
        if match:
            client_name = match.group(1).strip()[:100]

    # Try to extract deadline from text
    deadline = None
    if "Abgabe" in full_text or "Frist" in full_text:
        deadline = _parse_date(full_text)

    return {
        "external_id": external_id,
        "url": url,
        "title": title,
        "client_name": client_name,
        "deadline": deadline,
    }


async def parse_detail_page(page: Page, external_id: str, url: str) -> Optional[RawProject]:
    """Parse a tender detail page.

    Args:
        page: Playwright page with loaded detail page
        external_id: External ID for this tender
        url: URL of the detail page

    Returns:
        RawProject or None
    """
    # Extract title
    title = None
    title_selectors = ["h1", ".tender-title", ".ausschreibung-titel", "article h1"]
    for sel in title_selectors:
        el = await page.query_selector(sel)
        if el:
            title = (await el.inner_text()).strip()
            if title and len(title) > 5:
                break

    if not title:
        return None

    # Extract description
    description = None
    desc_selectors = [
        ".description", ".beschreibung", ".tender-description",
        ".content", "article .text", ".detail-content"
    ]
    for sel in desc_selectors:
        el = await page.query_selector(sel)
        if el:
            description = (await el.inner_text()).strip()
            if description:
                break

    # Extract client
    client_name = None
    client_selectors = [
        ".auftraggeber", ".client", ".vergabestelle",
        "[data-field='client']", ".organization"
    ]
    for sel in client_selectors:
        el = await page.query_selector(sel)
        if el:
            client_name = (await el.inner_text()).strip()
            if client_name:
                break

    # Extract deadline
    deadline = None
    deadline_selectors = [
        ".deadline", ".frist", ".abgabefrist",
        "[data-field='deadline']", ".submission-date"
    ]
    for sel in deadline_selectors:
        el = await page.query_selector(sel)
        if el:
            text = await el.inner_text()
            deadline = _parse_date(text)
            if deadline:
                break

    # Extract location
    location = None
    location_selectors = [".location", ".ort", ".standort", "[data-field='location']"]
    for sel in location_selectors:
        el = await page.query_selector(sel)
        if el:
            location = (await el.inner_text()).strip()
            if location:
                break

    # Check for remote keywords
    full_text = f"{title} {description or ''} {location or ''}".lower()
    remote = any(kw in full_text for kw in ["remote", "homeoffice", "home-office"])

    return RawProject(
        source="evergabe",
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
    """Extract PDF download links from detail page.

    Args:
        page: Playwright page
        max_pdfs: Maximum number of PDFs to extract

    Returns:
        List of dicts with 'url' and 'title' keys
    """
    pdf_links = []

    # Find PDF links
    links = await page.query_selector_all("a[href*='.pdf'], a[href*='download']")

    for link in links[:max_pdfs * 2]:  # Check more to filter
        try:
            href = await link.get_attribute("href")
            if not href:
                continue

            # Must be PDF or likely PDF download
            if ".pdf" not in href.lower() and "download" not in href.lower():
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
    """Normalize URL (add base if relative)."""
    if url.startswith("/"):
        return f"https://www.evergabe.de{url}"
    if not url.startswith("http"):
        return f"https://www.evergabe.de/{url}"
    return url


def _parse_date(text: str) -> Optional[datetime]:
    """Parse date from text."""
    if not text:
        return None

    # German date formats
    patterns = [
        r"(\d{1,2})[./](\d{1,2})[./](\d{4})",
        r"(\d{4})-(\d{2})-(\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                groups = match.groups()
                if len(groups[0]) == 4:  # ISO format
                    return datetime(int(groups[0]), int(groups[1]), int(groups[2]))
                else:  # German format
                    return datetime(int(groups[2]), int(groups[1]), int(groups[0]))
            except ValueError:
                continue

    return None
