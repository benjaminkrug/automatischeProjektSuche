"""HTML parsing for TED (Tenders Electronic Daily) pages."""

import re
from datetime import datetime
from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> list[dict]:
    """Parse TED search results page to extract tender links."""
    results = []
    seen_ids = set()

    try:
        # Wait for table or notice links to load
        await page.wait_for_selector(
            "a[href*='/notice/'], table tr",
            timeout=15000
        )
    except Exception:
        return results

    # Give dynamic content extra time to load
    await page.wait_for_timeout(2000)

    # Find all notice links directly (TED 2024+ uses table-based layout)
    links = await page.query_selector_all("a[href*='/notice/-/detail/']")

    for link in links:
        try:
            href = await link.get_attribute("href")
            if not href:
                continue

            # Extract notice ID from URL (format: /notice/-/detail/12345-2026)
            id_match = re.search(r"/notice/-/detail/([0-9-]+)", href)
            if not id_match:
                id_match = re.search(r"/notice[s]?/([0-9-]+)", href)
            if not id_match:
                continue

            external_id = id_match.group(1)

            # Skip duplicates
            if external_id in seen_ids:
                continue
            seen_ids.add(external_id)

            # Get title from link text or parent row
            title_text = await link.inner_text()
            title_text = title_text.strip()

            # If title is just the ID, try to get more context from parent
            if title_text == external_id or len(title_text) < 10:
                try:
                    parent_row = await link.evaluate_handle("el => el.closest('tr')")
                    if parent_row:
                        row_text = await parent_row.inner_text()
                        # Use row text but clean it up
                        title_text = " ".join(row_text.split()[:15])
                except Exception:
                    pass

            if not title_text or len(title_text) < 5:
                title_text = f"TED Notice {external_id}"

            if not href.startswith("http"):
                href = f"https://ted.europa.eu{href}"

            results.append({
                "external_id": external_id,
                "title": title_text,
                "url": href
            })

        except Exception:
            continue

    return results


async def parse_detail_page(page: Page, external_id: str, url: str) -> RawProject | None:
    """Parse TED tender detail page to extract full information."""
    try:
        await page.wait_for_selector("main, article, .notice-detail", timeout=10000)
    except Exception:
        return None

    # Extract title
    title = ""
    title_el = await page.query_selector("h1, .notice-title")
    if title_el:
        title = await title_el.inner_text()
    title = title.strip() or f"Ausschreibung {external_id}"

    # Extract contracting authority (client)
    client_name = None
    client_selectors = [
        "[data-label='Contracting authority'] dd",
        ".contracting-authority",
        "dt:has-text('Contracting') + dd",
        "dt:has-text('Auftraggeber') + dd"
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
        ".notice-description",
        "[data-label='Description'] dd",
        ".description",
        "dt:has-text('Description') + dd",
        "dt:has-text('Beschreibung') + dd"
    ]
    for selector in desc_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                description = await el.inner_text()
                if len(description) > 50:
                    break
        except Exception:
            continue

    # Extract location (country)
    location = None
    location_selectors = [
        "[data-label='Place'] dd",
        ".location",
        "dt:has-text('Place') + dd",
        "dt:has-text('Erfüllungsort') + dd"
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
        "[data-label='Deadline'] dd",
        ".deadline",
        "dt:has-text('Deadline') + dd",
        "dt:has-text('Frist') + dd"
    ]
    for selector in deadline_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                deadline_text = await el.inner_text()
                # Try to parse date format (DD/MM/YYYY or YYYY-MM-DD)
                date_match = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", deadline_text)
                if date_match:
                    # Try different date formats
                    try:
                        deadline = datetime(
                            int(date_match.group(3)),
                            int(date_match.group(2)),
                            int(date_match.group(1))
                        )
                    except ValueError:
                        # Try YYYY-MM-DD format
                        deadline = datetime(
                            int(date_match.group(1)),
                            int(date_match.group(2)),
                            int(date_match.group(3))
                        )
                break
        except Exception:
            continue

    # Extract CPV codes (skills equivalent)
    skills = []
    cpv_selectors = [
        "[data-label='CPV'] dd",
        ".cpv-codes span",
        "dt:has-text('CPV') + dd"
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

    # Check if remote work mentioned
    page_text = await page.inner_text("body")
    remote = any(term in page_text.lower() for term in ["remote", "teleworking", "home-based"])

    return RawProject(
        source="ted",
        external_id=external_id,
        url=url,
        title=title,
        client_name=client_name.strip() if client_name else None,
        description=description.strip() if description else None,
        skills=skills,
        budget=None,  # Usually not disclosed in TED
        location=location.strip() if location else None,
        remote=remote,
        public_sector=True,  # TED is always public sector
        deadline=deadline,
    )
