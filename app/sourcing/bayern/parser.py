"""Parser for Bayern Vergabeportal (vergabe.bayern.de) search results."""

import re
from datetime import datetime
from typing import List, Optional

from app.core.logging import get_logger
from app.sourcing.base import RawProject, extract_cpv_codes

logger = get_logger("sourcing.bayern.parser")


async def parse_search_results(page) -> List[dict]:
    """Parse search results page into raw data dictionaries.

    Args:
        page: Playwright page object

    Returns:
        List of dictionaries with tender data
    """
    results = []

    try:
        # Wait for results to load
        await page.wait_for_selector(
            "table, .tender-list, .search-results, .result-item",
            timeout=10000,
        )

        # Try multiple selectors
        selectors = [
            "table.results tbody tr",
            ".tender-item",
            ".search-result-item",
            ".vergabe-item",
            "[data-tender-id]",
        ]

        items = []
        for selector in selectors:
            items = await page.query_selector_all(selector)
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

    Args:
        item: Playwright element handle

    Returns:
        Dictionary with tender data or None
    """
    data = {}

    # Try table row format first (common in government portals)
    cells = await item.query_selector_all("td")
    if cells and len(cells) >= 3:
        # Table format: typically ID | Title | Authority | Deadline
        if len(cells) >= 1:
            cell_text = await cells[0].inner_text()
            # First cell might be ID or title
            if re.match(r"^\d{4,}$", cell_text.strip()):
                data["external_id"] = cell_text.strip()
                if len(cells) >= 2:
                    title_cell = cells[1]
                    data["title"] = (await title_cell.inner_text()).strip()
                    href = await title_cell.query_selector("a")
                    if href:
                        data["url"] = await href.get_attribute("href")
            else:
                # First cell is probably title
                data["title"] = cell_text.strip()
                link = await cells[0].query_selector("a")
                if link:
                    data["url"] = await link.get_attribute("href")

        # Extract client
        if len(cells) >= 3:
            data["client_name"] = (await cells[2].inner_text()).strip()

        # Extract deadline (usually last or second-to-last cell)
        if len(cells) >= 4:
            deadline_text = await cells[-1].inner_text()
            data["deadline"] = _parse_date(deadline_text.strip())

    else:
        # Non-table format
        # Extract title
        title_el = await item.query_selector(
            "h3, h4, .title, .tender-title, a.result-link"
        )
        if title_el:
            data["title"] = (await title_el.inner_text()).strip()
            href = await title_el.get_attribute("href")
            if href:
                data["url"] = href

        # Extract external ID
        id_el = await item.query_selector(".tender-id, .reference-number")
        if id_el:
            data["external_id"] = (await id_el.inner_text()).strip()

        # Extract client
        client_el = await item.query_selector(".authority, .client, .vergabestelle")
        if client_el:
            data["client_name"] = (await client_el.inner_text()).strip()

        # Extract deadline
        deadline_el = await item.query_selector(".deadline, .frist, .abgabefrist")
        if deadline_el:
            data["deadline"] = _parse_date((await deadline_el.inner_text()).strip())

    # Generate ID from URL if missing
    if not data.get("external_id") and data.get("url"):
        match = re.search(r"(?:id|oid|tender)=(\d+)|/(\d+)(?:\?|$)", data["url"])
        if match:
            data["external_id"] = match.group(1) or match.group(2)

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
        for selector in ["h1", "h2.title", ".tender-title", ".detail-title"]:
            el = await page.query_selector(selector)
            if el:
                title = (await el.inner_text()).strip()
                if title:
                    break

        # Extract description
        description = ""
        for selector in [
            ".description", ".tender-description", ".leistung",
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
        for selector in [".deadline", ".abgabefrist", ".frist", "[data-deadline]"]:
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
                r"(?:abgabe|einreichung|frist|deadline)[^\d]*(\d{1,2}\.\d{1,2}\.\d{2,4})",
                page_text.lower(),
            )
            if match:
                deadline = _parse_date(match.group(1))

        # Extract CPV codes
        cpv_codes = extract_cpv_codes(await page.inner_text("body"))

        # Extract budget
        budget = None
        page_text = await page.inner_text("body")
        budget_match = re.search(
            r"(?:auftragswert|volumen|budget|schätzwert)[:\s]*(?:ca\.?\s*)?(\d+(?:[.,]\d+)?)\s*(mio|tsd|k|€|eur)?",
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
            source="bayern",
            external_id=external_id,
            url=url,
            title=title or f"Bayern Ausschreibung {external_id}",
            client_name=client_name,
            description=description,
            public_sector=True,
            project_type="tender",
            cpv_codes=cpv_codes,
            tender_deadline=deadline,
            budget_max=budget,
        )

    except Exception as e:
        logger.warning("Error parsing Bayern detail page: %s", e)
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
