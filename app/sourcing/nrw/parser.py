"""Parser for NRW Vergabeportal (evergabe.nrw.de) search results."""

import re
from datetime import datetime
from typing import List, Optional

from app.core.logging import get_logger
from app.sourcing.base import RawProject, extract_cpv_codes

logger = get_logger("sourcing.nrw.parser")


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
            ".tender-list, .search-results, table tbody tr, .result-item",
            timeout=10000,
        )

        # Try multiple selectors for different page structures
        selectors = [
            ".tender-item",
            ".search-result-item",
            ".result-row",
            "table.results tbody tr",
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

    # Extract title
    title_el = await item.query_selector(
        "h3, h4, .title, .tender-title, td:first-child a, .result-title"
    )
    if title_el:
        data["title"] = await title_el.inner_text()
        data["title"] = data["title"].strip()

        # Try to get URL from title link
        href = await title_el.get_attribute("href")
        if href:
            data["url"] = href if href.startswith("http") else f"https://www.evergabe.nrw.de{href}"

    # Extract external ID
    id_el = await item.query_selector(
        ".tender-id, .reference-number, [data-tender-id], td:nth-child(2)"
    )
    if id_el:
        data["external_id"] = (await id_el.inner_text()).strip()

    # Try data attribute
    if not data.get("external_id"):
        data["external_id"] = await item.get_attribute("data-tender-id")

    # Generate ID from URL if still missing
    if not data.get("external_id") and data.get("url"):
        match = re.search(r"id=(\d+)|/(\d+)", data["url"])
        if match:
            data["external_id"] = match.group(1) or match.group(2)

    # Extract client/authority
    client_el = await item.query_selector(
        ".authority, .client, .contracting-authority, td:nth-child(3)"
    )
    if client_el:
        data["client_name"] = (await client_el.inner_text()).strip()

    # Extract deadline
    deadline_el = await item.query_selector(
        ".deadline, .submission-date, td:nth-child(4), [data-deadline]"
    )
    if deadline_el:
        deadline_text = await deadline_el.inner_text()
        data["deadline"] = _parse_date(deadline_text.strip())

    # Extract publication date
    pub_el = await item.query_selector(
        ".publication-date, .published, td:nth-child(5)"
    )
    if pub_el:
        pub_text = await pub_el.inner_text()
        data["published_at"] = _parse_date(pub_text.strip())

    # Extract description if available
    desc_el = await item.query_selector(
        ".description, .summary, .tender-description"
    )
    if desc_el:
        data["description"] = (await desc_el.inner_text()).strip()

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

        # Extract title
        title = ""
        for selector in ["h1", ".tender-title", ".detail-title", "#title"]:
            el = await page.query_selector(selector)
            if el:
                title = (await el.inner_text()).strip()
                if title:
                    break

        # Extract description
        description = ""
        for selector in [".description", ".tender-description", ".content", "#description"]:
            el = await page.query_selector(selector)
            if el:
                description = (await el.inner_text()).strip()
                if description:
                    break

        # Extract client
        client_name = ""
        for selector in [".authority", ".client-name", ".contracting-authority"]:
            el = await page.query_selector(selector)
            if el:
                client_name = (await el.inner_text()).strip()
                if client_name:
                    break

        # Extract deadline
        deadline = None
        for selector in [".deadline", ".submission-deadline", "[data-deadline]"]:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                deadline = _parse_date(text.strip())
                if deadline:
                    break

        # Extract CPV codes from page text
        page_text = await page.inner_text("body")
        cpv_codes = extract_cpv_codes(page_text)

        # Extract budget if present
        budget = None
        budget_match = re.search(
            r"(?:budget|volumen|wert|auftragswert)[:\s]*(?:ca\.?\s*)?(\d+(?:[.,]\d+)?)\s*(mio|tsd|k|€|eur)?",
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
