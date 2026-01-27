"""HTML parsing for Vergabe24 portal pages."""

import re
from datetime import datetime
from typing import List, Optional

from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> List[dict]:
    """Parse Vergabe24 search results page to extract tender links.

    Args:
        page: Playwright page with loaded search results

    Returns:
        List of dicts with external_id, title, url, client_name, deadline_text
    """
    results = []

    try:
        # Wait for results to load - Vergabe24 uses Bricks Builder + Splide carousel
        await page.wait_for_selector(
            ".teaser-card-big, article, .ausschreibung-item, .tender-item",
            timeout=15000
        )
    except Exception:
        return results

    # Vergabe24 uses Bricks Builder with Splide carousel for tender cards
    items = await page.query_selector_all(
        ".teaser-card-big, .teaser-card, article, "
        ".ausschreibung-item, .tender-item, .search-result-item"
    )

    for item in items:
        try:
            # Find the main link - Vergabe24 uses various link patterns
            link = await item.query_selector(
                "a[href*='ausschreibung'], a[href*='vergabe'], a[href*='tender'], "
                ".teaser-card-big__inner a, .teaser-card__inner a, "
                "h2 a, h3 a, .entry-title a, .teaser-card-big__heading a"
            )

            if not link:
                # Try to find any link in the card
                link = await item.query_selector("a[href]")

            if not link:
                continue

            href = await link.get_attribute("href")

            # Try to get title from heading elements
            title_text = None
            title_selectors = [
                ".teaser-card-big__heading",
                ".teaser-card__heading",
                "h2", "h3", ".heading", ".title"
            ]
            for selector in title_selectors:
                title_el = await item.query_selector(selector)
                if title_el:
                    title_text = await title_el.inner_text()
                    if title_text and title_text.strip():
                        break

            # Fall back to link text
            if not title_text:
                title_text = await link.inner_text()

            if not href or not title_text:
                continue

            # Skip navigation/filter links
            if len(title_text.strip()) < 10:
                continue

            # Extract external ID from URL
            external_id = _extract_external_id(href)
            if not external_id:
                continue

            # Build full URL if relative
            if not href.startswith("http"):
                href = f"https://www.vergabe24.de{href}"

            # Try to extract client/contracting authority
            client_name = None
            client_selectors = [
                ".teaser-card-big__meta", ".teaser-card__meta",
                ".auftraggeber", ".vergabestelle", ".client",
                ".entry-meta", ".tender-client"
            ]
            for selector in client_selectors:
                client_el = await item.query_selector(selector)
                if client_el:
                    client_name = await client_el.inner_text()
                    if client_name and client_name.strip():
                        break

            # Try to extract deadline
            deadline_text = None
            deadline_selectors = [
                ".deadline", ".frist", ".date", "time",
                ".entry-date", ".tender-deadline",
                "[class*='date']", "[class*='deadline']"
            ]
            for selector in deadline_selectors:
                deadline_el = await item.query_selector(selector)
                if deadline_el:
                    deadline_text = await deadline_el.inner_text()
                    if deadline_text and deadline_text.strip():
                        break

            # Try to extract excerpt/description
            excerpt = None
            excerpt_selectors = [
                ".teaser-card-big__content", ".teaser-card__content",
                ".excerpt", ".entry-summary", ".description",
                ".tender-excerpt", "p"
            ]
            for selector in excerpt_selectors:
                excerpt_el = await item.query_selector(selector)
                if excerpt_el:
                    excerpt = await excerpt_el.inner_text()
                    if excerpt and len(excerpt.strip()) > 20:
                        break

            results.append({
                "external_id": external_id,
                "title": title_text.strip(),
                "url": href,
                "client_name": client_name.strip() if client_name else None,
                "deadline_text": deadline_text.strip() if deadline_text else None,
                "excerpt": excerpt.strip() if excerpt else None,
            })

        except Exception:
            continue

    return results


async def parse_detail_page(page: Page, external_id: str, url: str) -> Optional[RawProject]:
    """Parse Vergabe24 tender detail page.

    Args:
        page: Playwright page with loaded detail page
        external_id: Unique tender identifier
        url: Full URL to the detail page

    Returns:
        RawProject with extracted data, or None on failure
    """
    try:
        await page.wait_for_selector(
            "article, main, .entry-content, .tender-detail",
            timeout=10000
        )
    except Exception:
        return None

    # Extract title
    title = ""
    title_selectors = [
        "h1", ".entry-title", ".tender-title",
        ".ausschreibung-title", "article header h1"
    ]
    for selector in title_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                title = await el.inner_text()
                if title.strip():
                    break
        except Exception:
            continue
    title = title.strip() or f"Ausschreibung {external_id}"

    # Extract client/contracting authority
    client_name = None
    client_selectors = [
        ".vergabestelle", ".auftraggeber", ".client",
        "dt:has-text('Vergabestelle') + dd",
        "dt:has-text('Auftraggeber') + dd",
        "strong:has-text('Vergabestelle') + span",
        "strong:has-text('Auftraggeber') + span",
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
        ".entry-content", ".tender-description", ".description",
        ".leistungsbeschreibung", "article .content",
        "dt:has-text('Beschreibung') + dd",
        "dt:has-text('Leistung') + dd",
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
        "strong:has-text('Ort') + span",
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
        "time[datetime]",
    ]
    for selector in deadline_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
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
        ".cpv", ".cpv-codes", ".kategorie",
        "dt:has-text('CPV') + dd",
        "strong:has-text('CPV') + span",
    ]
    for selector in cpv_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                cpv_text = await el.inner_text()
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
        source="vergabe24",
        external_id=external_id,
        url=url,
        title=title,
        client_name=client_name.strip() if client_name else None,
        description=description.strip() if description else None,
        skills=skills,
        budget=None,
        location=location.strip() if location else None,
        remote=remote,
        public_sector=True,  # Vergabe24 is always public sector
        deadline=deadline,
    )


def _extract_external_id(url: str) -> Optional[str]:
    """Extract unique tender ID from Vergabe24 URL.

    Args:
        url: URL to parse

    Returns:
        Extracted ID or None
    """
    # Try common URL patterns
    patterns = [
        r"/ausschreibung[/-]([0-9a-zA-Z_-]+)",
        r"/vergabe[/-]([0-9a-zA-Z_-]+)",
        r"[?&]id=([0-9a-zA-Z_-]+)",
        r"/p/([0-9]+)",
        r"/([0-9]{5,})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)

    # Fallback: use URL slug as ID
    path = url.split("?")[0].rstrip("/")
    if "/" in path:
        last_segment = path.split("/")[-1]
        if last_segment and len(last_segment) >= 5:
            # Clean up the slug
            slug = re.sub(r"[^a-zA-Z0-9_-]", "", last_segment)
            if slug:
                return slug

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

    return None
