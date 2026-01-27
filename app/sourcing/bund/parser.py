"""HTML parsing for bund.de tender pages."""

import re
from datetime import datetime
from playwright.async_api import Page

from app.sourcing.base import RawProject


def _is_valid_tender_link(href: str, title: str) -> bool:
    """Check if a link is a valid tender link (not navigation/form)."""
    if not href or not title:
        return False

    # Skip if title is too short or generic
    if len(title) < 15:
        return False

    # Skip generic navigation titles
    skip_titles = [
        "ausschreibungen", "suche", "formular", "filter",
        "zurück", "weiter", "next", "previous", "mehr"
    ]
    title_lower = title.lower().strip()
    if title_lower in skip_titles:
        return False

    # Skip form/navigation links
    skip_patterns = [
        "?view=", "?type=", "Formular", "Suche",
        "javascript:", "#", "mailto:", "tel:"
    ]
    for pattern in skip_patterns:
        if pattern in href:
            return False

    # Must contain indicator of actual tender detail page
    valid_patterns = [
        "IMPORTE/Ausschreibungen/",
        "/Ausschreibungen/",
        "/eVergabe/", "/vergabe/", "/ausschreibung/",
        "id=", "tender", "notice",
        ".html"
    ]
    has_valid_pattern = any(p.lower() in href.lower() for p in valid_patterns)

    return has_valid_pattern


def _build_url(href: str) -> str:
    """Build full URL from href."""
    if href.startswith("http"):
        return href
    # Ensure proper path separator
    if not href.startswith("/"):
        href = "/" + href
    return f"https://www.service.bund.de{href}"


def _extract_external_id(href: str) -> str:
    """Extract a unique external ID from the URL."""
    # Try to extract numeric ID from URL parameters
    id_match = re.search(r"[?&]id=(\d+)", href)
    if id_match:
        return id_match.group(1)

    # Try to extract from path (pattern: IMPORTE/Ausschreibungen/source/date/id.html)
    # Example: IMPORTE/Ausschreibungen/xyz/2024-01-15/12345.html
    id_match = re.search(r"/(\d+)\.html", href)
    if id_match:
        return id_match.group(1)

    # Try to extract from path - any 5+ digit sequence
    id_match = re.search(r"/(\d{5,})(?:[/?.]|$)", href)
    if id_match:
        return id_match.group(1)

    # Extract filename without extension as ID
    filename_match = re.search(r"/([^/]+)\.html$", href)
    if filename_match:
        return filename_match.group(1)

    # Use hash of URL as fallback for uniqueness
    import hashlib
    return hashlib.md5(href.encode()).hexdigest()[:16]


async def parse_search_results(page: Page) -> list[dict]:
    """Parse search results page to extract tender links.

    Args:
        page: Playwright page with search results loaded

    Returns:
        List of dicts with id, title, url for each tender
    """
    results = []
    seen_ids = set()

    # Wait for results to load after form submission
    try:
        await page.wait_for_selector("a[href*='IMPORTE/Ausschreibungen/']", timeout=15000)
    except Exception:
        return results

    # Give dynamic content time to load
    await page.wait_for_timeout(2000)

    # Find all IMPORTE/Ausschreibungen links (actual tender detail links)
    links = await page.query_selector_all("a[href*='IMPORTE/Ausschreibungen/']")

    for link in links:
        try:
            href = await link.get_attribute("href")
            if not href:
                continue

            # Must be a .html page (actual tender, not a filter)
            if ".html" not in href:
                continue

            title = await link.inner_text()
            if not title:
                continue

            # Clean up title - often has "Ausschreibung\n<title>\n\nVergabestelle\n<name>" format
            title_clean = title.strip()
            if "Ausschreibung" in title_clean:
                title_clean = title_clean.replace("Ausschreibung", "").strip()
            if "Vergabestelle" in title_clean:
                title_clean = title_clean.split("Vergabestelle")[0].strip()

            # Remove soft hyphens and clean whitespace
            title_clean = title_clean.replace("\u00ad", "").replace("\n", " ")
            title_clean = " ".join(title_clean.split())  # Normalize whitespace

            # Skip titles that are too short (likely navigation)
            if len(title_clean) < 15:
                continue

            external_id = _extract_external_id(href)

            # Skip duplicates
            if external_id in seen_ids:
                continue
            seen_ids.add(external_id)

            results.append({
                "external_id": external_id,
                "title": title_clean,
                "url": _build_url(href)
            })

        except Exception:
            continue

    return results


async def parse_detail_page(page: Page, external_id: str, url: str) -> RawProject | None:
    """Parse tender detail page to extract full information.

    Args:
        page: Playwright page with detail page loaded
        external_id: External ID from search results
        url: URL of the detail page

    Returns:
        RawProject with extracted data, or None if parsing failed
    """
    try:
        await page.wait_for_selector("main, article, .content", timeout=10000)
    except Exception:
        return None

    # Extract title
    title = ""
    title_el = await page.query_selector("h1")
    if title_el:
        title = await title_el.inner_text()
    title = title.strip() or f"Ausschreibung {external_id}"

    # Extract client/organization
    client_name = None
    client_selectors = [
        "dt:has-text('Auftraggeber') + dd",
        "dt:has-text('Vergabestelle') + dd",
        ".client-name",
        "[data-label='Auftraggeber']"
    ]
    for selector in client_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                client_name = await el.inner_text()
                break
        except Exception:
            continue

    # Extract description
    description = ""
    desc_selectors = [
        "dt:has-text('Beschreibung') + dd",
        "dt:has-text('Leistungsbeschreibung') + dd",
        ".description",
        "[data-label='Beschreibung']",
        "article p"
    ]
    for selector in desc_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                description = await el.inner_text()
                break
        except Exception:
            continue

    # Extract location
    location = None
    location_selectors = [
        "dt:has-text('Erfüllungsort') + dd",
        "dt:has-text('Ort') + dd",
        ".location"
    ]
    for selector in location_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                location = await el.inner_text()
                break
        except Exception:
            continue

    # Extract deadline
    deadline = None
    deadline_selectors = [
        "dt:has-text('Angebotsfrist') + dd",
        "dt:has-text('Frist') + dd",
        ".deadline"
    ]
    for selector in deadline_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                deadline_text = await el.inner_text()
                # Try to parse German date format
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", deadline_text)
                if date_match:
                    deadline = datetime(
                        int(date_match.group(3)),
                        int(date_match.group(2)),
                        int(date_match.group(1))
                    )
                break
        except Exception:
            continue

    # Extract skills/categories
    skills = []
    cpv_el = await page.query_selector("dt:has-text('CPV') + dd, .cpv-codes")
    if cpv_el:
        cpv_text = await cpv_el.inner_text()
        # Extract keywords from CPV descriptions
        keywords = re.findall(r"[A-ZÄÖÜ][a-zäöüß]+(?:[-][A-Za-zäöüß]+)?", cpv_text)
        skills.extend(keywords[:10])

    # Check if remote work mentioned
    page_text = await page.inner_text("body")
    remote = any(term in page_text.lower() for term in ["remote", "homeoffice", "home-office", "telearbeit"])

    return RawProject(
        source="bund.de",
        external_id=external_id,
        url=url,
        title=title,
        client_name=client_name.strip() if client_name else None,
        description=description.strip() if description else None,
        skills=skills,
        budget=None,  # Usually not disclosed
        location=location.strip() if location else None,
        remote=remote,
        public_sector=True,  # Always public sector
        deadline=deadline,
    )


# Keywords for identifying relevant PDFs on bund.de
_PDF_KEYWORDS = [
    "leistungsverzeichnis",
    "vergabeunterlagen",
    "leistungsbeschreibung",
    "lv",
    "lvb",
    "anforderung",
    "spezifikation",
    "pflichtenheft",
    "lastenheft",
    "ausschreibung",
]


async def extract_pdf_links(page: Page, max_pdfs: int = 3) -> list[dict]:
    """Extract relevant PDF links from a bund.de tender detail page.

    Args:
        page: Playwright page with tender detail loaded
        max_pdfs: Maximum number of PDFs to return

    Returns:
        List of dicts with 'url' and 'title' keys
    """
    pdf_links = []
    seen_urls = set()

    try:
        # Find all PDF links - bund.de uses various patterns
        selectors = [
            "a[href$='.pdf']",
            "a[href*='download'][href*='.pdf']",
            "a[href*='/IMPORTE/'][href$='.pdf']",
            "a.download-link",
            ".dokumente a[href$='.pdf']",
            ".downloads a[href$='.pdf']",
            ".unterlagen a[href$='.pdf']",
        ]

        for selector in selectors:
            try:
                links = await page.query_selector_all(selector)
                for link in links:
                    try:
                        href = await link.get_attribute("href")
                        if not href:
                            continue

                        # Build full URL if relative
                        if href.startswith("/"):
                            href = f"https://www.service.bund.de{href}"
                        elif not href.startswith("http"):
                            continue

                        # Skip duplicates
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)

                        # Get link text
                        text = await link.inner_text()
                        text = (text or "").strip()

                        # Also check aria-label and title attributes
                        aria = await link.get_attribute("aria-label") or ""
                        title_attr = await link.get_attribute("title") or ""
                        context = f"{text} {aria} {title_attr}".lower()

                        pdf_links.append({
                            "url": href,
                            "title": text[:100] if text else "",
                            "context": context,
                        })

                    except Exception:
                        continue
            except Exception:
                continue

    except Exception:
        pass

    # Score by relevance (keywords in title/context)
    def relevance_score(pdf: dict) -> int:
        score = 0
        context = pdf.get("context", "").lower()
        for keyword in _PDF_KEYWORDS:
            if keyword in context:
                score += 10
        return score

    pdf_links.sort(key=relevance_score, reverse=True)

    return pdf_links[:max_pdfs]
