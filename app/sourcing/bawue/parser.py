"""Parser for Baden-Württemberg Vergabeportal (vergabe.landbw.de) search results."""

import re
from datetime import datetime
from typing import List, Optional

from app.core.logging import get_logger
from app.sourcing.base import RawProject, extract_cpv_codes

logger = get_logger("sourcing.bawue.parser")


async def parse_search_results(page) -> List[dict]:
    """Parse search results page into raw data dictionaries.

    BaWü portal structure (table columns):
    0. Erschienen am (publication date)
    1. Ausschreibung (title)
    2. Vergabestelle (client)
    3. Verfahrensart (procedure type)
    4. Rechtsrahmen (legal framework)
    5. Abgabefrist (deadline)

    Note: Table cells have NO links - data is display-only.

    Args:
        page: Playwright page object

    Returns:
        List of dictionaries with tender data
    """
    results = []

    try:
        # Wait for table to load
        await page.wait_for_selector("table tbody tr, table tr", timeout=15000)

        # Get all table rows
        rows = await page.query_selector_all("table tbody tr, table tr")
        logger.debug("Found %d table rows", len(rows))

        for row in rows:
            # Skip header rows
            th = await row.query_selector("th")
            if th:
                continue

            cells = await row.query_selector_all("td")
            if len(cells) < 3:
                continue

            try:
                data = await _parse_table_row(cells)
                if data and data.get("title"):
                    results.append(data)
            except Exception as e:
                logger.debug("Error parsing row: %s", e)
                continue

    except Exception as e:
        logger.warning("Error parsing search results: %s", e)

    return results


async def _parse_table_row(cells) -> Optional[dict]:
    """Parse a table row from BaWü portal.

    Columns:
    0. Erschienen am (publication date)
    1. Ausschreibung (title)
    2. Vergabestelle (client)
    3. Verfahrensart (procedure type)
    4. Rechtsrahmen (legal framework)
    5. Abgabefrist (deadline)

    Args:
        cells: List of td elements

    Returns:
        Dictionary with tender data or None
    """
    data = {}

    # Cell 0: Publication date
    if len(cells) >= 1:
        date_text = (await cells[0].inner_text()).strip()
        data["published_at"] = _parse_date(date_text)

    # Cell 1: Title (Ausschreibung)
    if len(cells) >= 2:
        title = (await cells[1].inner_text()).strip()
        data["title"] = title

    # Cell 2: Client (Vergabestelle)
    if len(cells) >= 3:
        client = (await cells[2].inner_text()).strip()
        data["client_name"] = client

    # Cell 5: Deadline (Abgabefrist)
    if len(cells) >= 6:
        deadline_text = (await cells[5].inner_text()).strip()
        data["deadline"] = _parse_date(deadline_text)

    # Generate external_id from title (no links available)
    if data.get("title"):
        import hashlib
        data["external_id"] = f"bawue_{hashlib.md5(data['title'].encode()).hexdigest()[:12]}"
        # No detail URL available - use search page
        data["url"] = "https://vergabe.landbw.de/NetServer/PublicationSearchControllerServlet"

    return data if data.get("title") else None


async def _parse_result_item(item) -> Optional[dict]:
    """Parse a single search result item (fallback for table format).

    Args:
        item: Playwright element handle

    Returns:
        Dictionary with tender data or None
    """
    data = {}

    # Try table row format
    cells = await item.query_selector_all("td")
    if cells and len(cells) >= 3:
        # Extract from table cells
        for i, cell in enumerate(cells):
            text = (await cell.inner_text()).strip()

            # First cell with link is usually title
            link = await cell.query_selector("a")
            if link and not data.get("title"):
                data["title"] = text
                href = await link.get_attribute("href")
                if href:
                    data["url"] = href if href.startswith("http") else f"https://vergabe.landbw.de{href}"
                    # Try to extract TenderOID
                    oid_match = re.search(r"TenderOID=([A-Za-z0-9_-]+)", href)
                    if oid_match:
                        data["external_id"] = oid_match.group(1)
                continue

            # Check for ID pattern
            if re.match(r"^\d{4,}$", text) and not data.get("external_id"):
                data["external_id"] = text
                continue

            # Check for date pattern
            date = _parse_date(text)
            if date:
                if not data.get("deadline"):
                    data["deadline"] = date
                elif not data.get("published_at"):
                    data["published_at"] = date

    else:
        # Non-table format
        title_selectors = [
            "h3 a", "h4 a", "h3", "h4",
            ".title", ".tender-title",
            "a.result-link", ".ausschreibung-titel",
        ]
        for selector in title_selectors:
            title_el = await item.query_selector(selector)
            if title_el:
                data["title"] = (await title_el.inner_text()).strip()
                href = await title_el.get_attribute("href")
                if href:
                    data["url"] = href if href.startswith("http") else f"https://vergabe.landbw.de{href}"
                if data["title"]:
                    break

        id_el = await item.query_selector(".tender-id, .reference-number, .vergabe-nr")
        if id_el:
            data["external_id"] = (await id_el.inner_text()).strip()

        client_el = await item.query_selector(
            ".authority, .client, .vergabestelle, .auftraggeber"
        )
        if client_el:
            data["client_name"] = (await client_el.inner_text()).strip()

        deadline_el = await item.query_selector(
            ".deadline, .frist, .abgabefrist, .einreichungsfrist"
        )
        if deadline_el:
            data["deadline"] = _parse_date((await deadline_el.inner_text()).strip())

    # Extract ID from URL if missing
    if not data.get("external_id") and data.get("url"):
        match = re.search(r"TenderOID=([A-Za-z0-9_-]+)|(?:id|oid|tender|vergabe)=(\d+)", data["url"])
        if match:
            data["external_id"] = match.group(1) or match.group(2)

    # Generate ID from title if still missing
    if not data.get("external_id") and data.get("title"):
        import hashlib
        data["external_id"] = f"bawue_{hashlib.md5(data['title'].encode()).hexdigest()[:12]}"

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
        await page.wait_for_load_state("domcontentloaded")

        # Extract title
        title = ""
        for selector in ["h1", "h2.title", ".tender-title", ".ausschreibung-titel"]:
            el = await page.query_selector(selector)
            if el:
                title = (await el.inner_text()).strip()
                if title:
                    break

        # Extract description
        description = ""
        for selector in [
            ".description", ".tender-description", ".leistungsbeschreibung",
            ".ausschreibungstext", "#description", ".content-main"
        ]:
            el = await page.query_selector(selector)
            if el:
                description = (await el.inner_text()).strip()
                if description:
                    break

        # Extract client
        client_name = ""
        for selector in [
            ".vergabestelle", ".authority", ".auftraggeber",
            "td:contains('Vergabestelle') + td",
            "th:contains('Auftraggeber') + td"
        ]:
            try:
                el = await page.query_selector(selector)
                if el:
                    client_name = (await el.inner_text()).strip()
                    if client_name:
                        break
            except Exception:
                continue

        # Extract deadline
        deadline = None
        for selector in [".deadline", ".abgabefrist", ".frist", ".einreichungsfrist"]:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                deadline = _parse_date(text.strip())
                if deadline:
                    break

        # Look for deadline in labeled fields
        if not deadline:
            page_text = await page.inner_text("body")
            match = re.search(
                r"(?:abgabe|einreichung|frist|deadline|angebot)[^\d]*(\d{1,2}\.\d{1,2}\.\d{2,4})",
                page_text.lower(),
            )
            if match:
                deadline = _parse_date(match.group(1))

        # Extract CPV codes
        page_text = await page.inner_text("body")
        cpv_codes = extract_cpv_codes(page_text)

        # Extract budget
        budget = None
        budget_match = re.search(
            r"(?:auftragswert|volumen|budget|schätzwert|geschätzter\s+wert)[:\s]*(?:ca\.?\s*)?(\d+(?:[.,]\d+)?)\s*(mio|tsd|k|€|eur)?",
            page_text.lower(),
        )
        if budget_match:
            value = float(budget_match.group(1).replace(",", "."))
            unit = budget_match.group(2) or ""
            if "mio" in unit:
                budget = int(value * 1_000_000)
            elif "tsd" in unit or unit == "k":
                budget = int(value * 1_000)
            else:
                budget = int(value)

        return RawProject(
            source="bawue",
            external_id=external_id,
            url=url,
            title=title or f"BaWü Ausschreibung {external_id}",
            client_name=client_name,
            description=description,
            public_sector=True,
            project_type="tender",
            cpv_codes=cpv_codes,
            tender_deadline=deadline,
            budget_max=budget,
        )

    except Exception as e:
        logger.warning("Error parsing BaWü detail page: %s", e)
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

    text = re.sub(r"\s+", " ", text.strip())

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
