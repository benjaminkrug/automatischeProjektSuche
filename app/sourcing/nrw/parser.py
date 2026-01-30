"""Parser for NRW Vergabeportal (evergabe.nrw.de) search results."""

import re
from datetime import datetime
from typing import List, Optional

from app.core.logging import get_logger
from app.sourcing.base import RawProject, extract_cpv_codes

logger = get_logger("sourcing.nrw.parser")


async def parse_search_results(page) -> List[dict]:
    """Parse search results page into raw data dictionaries.

    NRW portal structure:
    - Table with sortable columns: Veröffentlicht, Frist, Kurzbezeichnung, Typ, Vergabeplattform
    - Each row contains tender data
    - Links use: projectForwarding.do?pid=[ID] or ENTER_PROJECTROOM

    Args:
        page: Playwright page object

    Returns:
        List of dictionaries with tender data
    """
    results = []

    try:
        # Wait for results table to load
        await page.wait_for_selector(
            "table tbody tr, .search-results, #searchResults",
            timeout=15000,
        )

        # NRW portal uses standard table structure
        selectors = [
            "table tbody tr",
            "table tr:not(:first-child)",  # Skip header row
            "[data-earmarked-id]",  # Rows with tender ID attribute
        ]

        items = []
        for selector in selectors:
            items = await page.query_selector_all(selector)
            if items:
                # Filter out header rows
                filtered_items = []
                for item in items:
                    # Skip rows that are header rows
                    th = await item.query_selector("th")
                    if not th:
                        filtered_items.append(item)
                items = filtered_items
                if items:
                    logger.debug("Found %d results with selector: %s", len(items), selector)
                    break

        for item in items:
            try:
                data = await _parse_result_item(item)
                if data and data.get("title"):
                    results.append(data)
            except Exception as e:
                logger.debug("Error parsing result item: %s", e)
                continue

    except Exception as e:
        logger.warning("Error parsing search results: %s", e)

    return results


async def _parse_result_item(item) -> Optional[dict]:
    """Parse a single search result item.

    NRW table structure (columns):
    1. Veröffentlicht (publication date)
    2. Angebots-/Teilnahmefrist (deadline)
    3. Kurzbezeichnung (title with link)
    4. Typ (VOB/A, UVgO, VgV, etc.)
    5. Vergabeplattform/Veröffentlicher (client)
    6. Aktion (link to Projektraum)

    Args:
        item: Playwright element handle (table row)

    Returns:
        Dictionary with tender data or None
    """
    data = {}

    # Get all cells in the row
    cells = await item.query_selector_all("td")
    if not cells or len(cells) < 3:
        return None

    # Column 1: Veröffentlicht (publication date)
    if len(cells) >= 1:
        pub_text = await cells[0].inner_text()
        data["published_at"] = _parse_date(pub_text.strip())

    # Column 2: Angebots-/Teilnahmefrist (deadline)
    if len(cells) >= 2:
        deadline_text = await cells[1].inner_text()
        data["deadline"] = _parse_date(deadline_text.strip())

    # Column 3: Kurzbezeichnung (title) - usually contains the main link
    if len(cells) >= 3:
        title_cell = cells[2]
        title_text = await title_cell.inner_text()
        data["title"] = title_text.strip()

        # Look for link in title cell
        link = await title_cell.query_selector("a")
        if link:
            href = await link.get_attribute("href")
            if href:
                data["url"] = href if href.startswith("http") else f"https://www.evergabe.nrw.de{href}"

    # Column 5: Vergabeplattform/Veröffentlicher (client)
    if len(cells) >= 5:
        client_text = await cells[4].inner_text()
        data["client_name"] = client_text.strip()

    # Column 6: Aktion - contains link to Projektraum
    if len(cells) >= 6:
        action_cell = cells[5]
        action_link = await action_cell.query_selector("a[href*='ENTER_PROJECTROOM'], a[href*='projectForwarding']")
        if action_link:
            href = await action_link.get_attribute("href")
            if href and not data.get("url"):
                data["url"] = href if href.startswith("http") else f"https://www.evergabe.nrw.de{href}"

    # Try to get earmarked-id from link
    earmarked_id = await item.get_attribute("data-earmarked-id")
    if earmarked_id:
        data["external_id"] = earmarked_id

    # Extract external ID from URL if not found
    if not data.get("external_id") and data.get("url"):
        # Pattern: pid=12345 or /12345
        match = re.search(r"pid=([A-Za-z0-9-]+)|id=([A-Za-z0-9-]+)", data["url"])
        if match:
            data["external_id"] = match.group(1) or match.group(2)

    # Generate ID from title if still missing
    if not data.get("external_id") and data.get("title"):
        # Create hash-based ID
        import hashlib
        data["external_id"] = f"nrw_{hashlib.md5(data['title'].encode()).hexdigest()[:12]}"

    return data if data.get("title") else None


async def parse_detail_page(page, external_id: str, url: str) -> Optional[RawProject]:
    """Parse tender detail page.

    Args:
        page: Playwright page object
        external_id: Tender ID
        url: Detail page URL

    Returns:
        RawProject or None
    """
    try:
        # Wait for content
        await page.wait_for_load_state("domcontentloaded")

        # Extract title - NRW portal typically uses h1 or h2
        title = ""
        title_selectors = [
            "h1",
            "h2",
            ".tender-title",
            ".detail-title",
            "#title",
            ".headline",
            "[ui-header] h1",
        ]
        for selector in title_selectors:
            el = await page.query_selector(selector)
            if el:
                title = (await el.inner_text()).strip()
                if title and len(title) > 5:
                    break

        # Extract description from various possible containers
        description = ""
        desc_selectors = [
            ".description",
            ".tender-description",
            ".content",
            "#description",
            ".detail-content",
            ".ausschreibung-text",
            "main .content",
        ]
        for selector in desc_selectors:
            el = await page.query_selector(selector)
            if el:
                description = (await el.inner_text()).strip()
                if description and len(description) > 20:
                    break

        # Extract client - look for Vergabestelle/Auftraggeber labels
        client_name = ""
        client_selectors = [
            ".authority",
            ".client-name",
            ".contracting-authority",
            ".vergabestelle",
            ".auftraggeber",
        ]
        for selector in client_selectors:
            el = await page.query_selector(selector)
            if el:
                client_name = (await el.inner_text()).strip()
                if client_name:
                    break

        # If no dedicated client element, search in page text
        if not client_name:
            page_text = await page.inner_text("body")
            client_match = re.search(
                r"(?:vergabestelle|auftraggeber|organisation)[:\s]*([^\n]+)",
                page_text.lower(),
            )
            if client_match:
                client_name = client_match.group(1).strip()[:200]

        # Extract deadline
        deadline = None
        deadline_selectors = [
            ".deadline",
            ".submission-deadline",
            "[data-deadline]",
            ".frist",
            ".abgabefrist",
        ]
        for selector in deadline_selectors:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                deadline = _parse_date(text.strip())
                if deadline:
                    break

        # Search for deadline in page text if not found
        if not deadline:
            page_text = await page.inner_text("body")
            deadline_match = re.search(
                r"(?:abgabe|einreichung|angebots|teilnahme)frist[:\s]*(\d{1,2}\.\d{1,2}\.\d{2,4})",
                page_text.lower(),
            )
            if deadline_match:
                deadline = _parse_date(deadline_match.group(1))

        # Extract CPV codes from page text
        page_text = await page.inner_text("body")
        cpv_codes = extract_cpv_codes(page_text)

        # Extract budget if present
        budget = None
        budget_match = re.search(
            r"(?:budget|volumen|wert|auftragswert|geschätzter\s+(?:auftrags)?wert)[:\s]*(?:ca\.?\s*)?(?:EUR\s*)?(\d+(?:[.,]\d+)?)\s*(mio|mio\.|million|tsd|tsd\.|k|€|eur)?",
            page_text.lower(),
        )
        if budget_match:
            value = float(budget_match.group(1).replace(",", "."))
            unit = budget_match.group(2) or ""
            if "mio" in unit or "million" in unit:
                budget = int(value * 1_000_000)
            elif "tsd" in unit or unit == "k":
                budget = int(value * 1_000)
            else:
                budget = int(value)

        return RawProject(
            source="nrw",
            external_id=external_id,
            url=url,
            title=title or f"NRW Ausschreibung {external_id}",
            client_name=client_name,
            description=description,
            public_sector=True,
            project_type="tender",
            cpv_codes=cpv_codes,
            tender_deadline=deadline,
            budget_max=budget,
        )

    except Exception as e:
        logger.warning("Error parsing NRW detail page: %s", e)
        return None


def _parse_date(text: str) -> Optional[datetime]:
    """Parse German date formats.

    Args:
        text: Date string

    Returns:
        datetime or None
    """
    if not text:
        return None

    # Clean up text
    text = re.sub(r"\s+", " ", text.strip())

    # Common German date formats
    formats = [
        "%d.%m.%Y",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y, %H:%M",
        "%d.%m.%Y %H:%M Uhr",
        "%d.%m.%y",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    # Try to extract date from longer text
    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text)
    if match:
        day, month, year = match.groups()
        if len(year) == 2:
            year = "20" + year
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass

    return None
