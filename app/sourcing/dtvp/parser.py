"""HTML parsing for DTVP (Deutsches Vergabeportal) pages."""

import re
from datetime import datetime
from typing import Optional

from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> list[dict]:
    """Parse DTVP search results page to extract tender links.

    DTVP categoryOverview.do returns a table with columns:
    [0] Veroeffentlicht | [1] Frist | [2] Kurzbezeichnung | [3] Typ | [4] Plattform | [5] Aktion

    The link to detail page is in the Aktion column (icon link with empty text).
    The title is in column 2 (Kurzbezeichnung).
    Detail URLs follow pattern: projectForwarding.do?pid=XXXXXX

    Args:
        page: Playwright page with loaded search results

    Returns:
        List of dicts with external_id, title, url, client_name, deadline
    """
    results = []

    try:
        # Wait for table to load (DTVP uses standard HTML tables)
        await page.wait_for_selector("table", timeout=15000)
    except Exception:
        return results

    # Find all table rows
    rows = await page.query_selector_all("tr")

    for row in rows:
        try:
            # Find link to detail page (projectForwarding.do pattern)
            link = await row.query_selector(
                "a[href*='projectForwarding.do'], "
                "a[href*='projectForwarding'], "
                "a[href*='pid=']"
            )

            if not link:
                continue

            href = await link.get_attribute("href")
            if not href:
                continue

            # Clean href (some have trailing '>')
            href = href.rstrip(">")

            # Extract PID (Project ID) from URL
            pid_match = re.search(r"pid=(\d+)", href)
            if pid_match:
                external_id = pid_match.group(1)
            else:
                # Fallback: use general ID extraction
                external_id = _extract_external_id(href)
                if not external_id:
                    continue

            # Build full URL if relative
            if not href.startswith("http"):
                if href.startswith("/"):
                    href = f"https://www.dtvp.de{href}"
                else:
                    href = f"https://www.dtvp.de/{href}"

            # Extract data from table cells
            # DTVP table structure:
            # [0] Veroeffentlicht, [1] Frist, [2] Kurzbezeichnung, [3] Typ, [4] Plattform, [5] Aktion
            cells = await row.query_selector_all("td")

            if len(cells) < 3:
                continue

            # Get title from column 2 (Kurzbezeichnung)
            title_text = await cells[2].inner_text()
            title_text = title_text.strip() if title_text else None

            if not title_text:
                continue

            # Get deadline from column 1 (Frist)
            deadline_text = None
            if len(cells) >= 2:
                deadline_text = await cells[1].inner_text()
                deadline_text = deadline_text.strip() if deadline_text else None

            results.append({
                "external_id": external_id,
                "title": title_text,
                "url": href,
                "client_name": None,  # Not available in search results
                "deadline_text": deadline_text,
            })

        except Exception:
            continue

    return results


async def parse_detail_page(page: Page, external_id: str, url: str) -> Optional[RawProject]:
    """Parse DTVP tender detail page to extract full information.

    DTVP detail pages redirect to /Satellite/public/company/project/...
    and have a tabbed interface. Basic info is available from page title
    and body text.

    Args:
        page: Playwright page with loaded detail page
        external_id: Unique tender identifier
        url: Full URL to the detail page

    Returns:
        RawProject with extracted data, or None on failure
    """
    # DTVP pages use a different structure - wait for any content
    try:
        await page.wait_for_selector(
            "body, h2, .content, main, article",
            timeout=5000  # Reduced timeout for faster fallback
        )
    except Exception:
        pass  # Continue anyway, try to extract what we can

    # Extract title from page title (most reliable on DTVP)
    # Format: "CXP4DSLMHY5 | Projektdatenbank für... | www.dtvp.de"
    title = ""
    try:
        page_title = await page.title()
        if page_title and "|" in page_title:
            parts = page_title.split("|")
            if len(parts) >= 2:
                title = parts[1].strip()
    except Exception:
        pass

    # Fallback: try h1/h2 selectors
    if not title:
        title_selectors = [
            "h1", "h2", ".notice-title", ".tender-title",
            ".ausschreibung-title", ".title"
        ]
        for selector in title_selectors:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.inner_text()
                    # Skip generic headers
                    if text.strip() and text.strip() not in ["Übersicht", "Overview"]:
                        title = text
                        break
            except Exception:
                continue

    title = title.strip() or f"Ausschreibung {external_id}"

    # Extract client/contracting authority
    client_name = None
    client_selectors = [
        ".vergabestelle", ".auftraggeber", ".client",
        ".contracting-authority", ".organization",
        "dt:has-text('Vergabestelle') + dd",
        "dt:has-text('Auftraggeber') + dd",
        "th:has-text('Vergabestelle') + td",
        "label:has-text('Vergabestelle') + span",
    ]
    for selector in client_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                client_name = await el.inner_text()
                if client_name.strip():
                    break
        except Exception:
            continue

    # Extract description
    description = ""
    desc_selectors = [
        ".description", ".beschreibung", ".notice-description",
        ".tender-description", ".leistungsbeschreibung",
        "dt:has-text('Beschreibung') + dd",
        "dt:has-text('Leistung') + dd",
        ".content p",
    ]
    for selector in desc_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                if len(text) > len(description):
                    description = text
        except Exception:
            continue

    # Extract location
    location = None
    location_selectors = [
        ".ort", ".location", ".erfuellungsort",
        "dt:has-text('Ort') + dd",
        "dt:has-text('Erfüllungsort') + dd",
    ]
    for selector in location_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                location = await el.inner_text()
                if location.strip():
                    break
        except Exception:
            continue

    # Extract deadline
    deadline = None
    deadline_selectors = [
        ".deadline", ".frist", ".angebotsfrist",
        "dt:has-text('Frist') + dd",
        "dt:has-text('Angebotsfrist') + dd",
        "th:has-text('Frist') + td",
        "time[datetime]",
    ]
    for selector in deadline_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                # Check for datetime attribute first
                datetime_attr = await el.get_attribute("datetime")
                if datetime_attr:
                    deadline = _parse_datetime(datetime_attr)
                else:
                    deadline_text = await el.inner_text()
                    deadline = _parse_datetime(deadline_text)
                if deadline:
                    break
        except Exception:
            continue

    # Extract CPV codes / skills
    skills = []
    cpv_selectors = [
        ".cpv", ".cpv-codes",
        "dt:has-text('CPV') + dd",
        "th:has-text('CPV') + td",
    ]
    for selector in cpv_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                cpv_text = await el.inner_text()
                # Extract keywords from CPV descriptions
                keywords = re.findall(r"[A-ZÄÖÜ][a-zäöüß]+(?:[-][A-Za-zäöüß]+)?", cpv_text)
                skills.extend(keywords[:10])
                break
        except Exception:
            continue

    # Check for remote work indication
    page_text = await page.inner_text("body")
    remote = any(term in page_text.lower() for term in [
        "remote", "homeoffice", "home-office", "telearbeit",
        "ortsunabhängig", "mobiles arbeiten"
    ])

    return RawProject(
        source="dtvp",
        external_id=external_id,
        url=url,
        title=title,
        client_name=client_name.strip() if client_name else None,
        description=description.strip() if description else None,
        skills=skills,
        budget=None,  # Usually not disclosed
        location=location.strip() if location else None,
        remote=remote,
        public_sector=True,  # DTVP is always public sector
        deadline=deadline,
    )


def _extract_external_id(url: str) -> Optional[str]:
    """Extract unique tender ID from DTVP URL.

    Args:
        url: URL to parse

    Returns:
        Extracted ID or None
    """
    # Try to match common DTVP URL patterns
    patterns = [
        r"[?&]pid=(\d+)",  # projectForwarding.do?pid=XXXXXX (primary pattern)
        r"/notice/([A-Za-z0-9_-]+)",
        r"/Satellite/.*?([A-Z]{2,}[0-9A-Za-z_-]+)",
        r"ausschreibung[/-]([0-9A-Za-z_-]+)",
        r"[?&]id=([0-9A-Za-z_-]+)",
        r"/([0-9]{6,})",  # Numeric IDs
    ]

    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)

    # Fallback: use last path segment
    path = url.split("?")[0].rstrip("/")
    if "/" in path:
        last_segment = path.split("/")[-1]
        if last_segment and len(last_segment) >= 5:
            return last_segment

    return None


def _parse_datetime(text: str) -> Optional[datetime]:
    """Parse German date/time formats.

    Args:
        text: Date string to parse

    Returns:
        Parsed datetime or None
    """
    if not text:
        return None

    text = text.strip()

    # Try ISO format first (YYYY-MM-DD)
    iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso_match:
        try:
            return datetime(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3))
            )
        except ValueError:
            pass

    # Try German format (DD.MM.YYYY)
    german_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if german_match:
        try:
            return datetime(
                int(german_match.group(3)),
                int(german_match.group(2)),
                int(german_match.group(1))
            )
        except ValueError:
            pass

    # Try other formats (DD/MM/YYYY)
    slash_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if slash_match:
        try:
            return datetime(
                int(slash_match.group(3)),
                int(slash_match.group(2)),
                int(slash_match.group(1))
            )
        except ValueError:
            pass

    return None
