"""HTML parsing for freelancermap.de project pages."""

import re
from datetime import datetime
from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> list[dict]:
    """Parse search results page to extract project links.

    Args:
        page: Playwright page with search results loaded

    Returns:
        List of dicts with id, title, url for each project
    """
    results = []

    # Wait for results to load
    try:
        await page.wait_for_selector(
            ".project-list, .project-item, [data-project-id]",
            timeout=10000
        )
    except Exception:
        return results

    # Find all project cards
    items = await page.query_selector_all(
        ".project-item, .project-card, article[data-project-id], "
        ".project-list-item, [data-testid='project-item']"
    )

    for item in items:
        try:
            # Try to find the project link
            link = await item.query_selector(
                "a[href*='/projekt/'], a[href*='/project/'], "
                "a.project-title, h2 a, h3 a"
            )

            if not link:
                continue

            href = await link.get_attribute("href")
            title_text = await link.inner_text()

            if not href or not title_text:
                continue

            # Extract external ID from URL - use full path segment for uniqueness
            # URLs like: /projekt/senior-it-consultant-2956131 or /projekt/some-slug
            path_segment = href.rstrip("/").split("/")[-1].replace(".html", "")
            external_id = path_segment if path_segment else href

            # Build full URL if needed
            if not href.startswith("http"):
                href = f"https://www.freelancermap.de{href}"

            results.append({
                "external_id": external_id,
                "title": title_text.strip(),
                "url": href
            })

        except Exception:
            continue

    return results


async def parse_detail_page(page: Page, external_id: str, url: str) -> RawProject | None:
    """Parse project detail page to extract full information.

    Args:
        page: Playwright page with detail page loaded
        external_id: External ID from search results
        url: URL of the detail page

    Returns:
        RawProject with extracted data, or None if parsing failed
    """
    try:
        await page.wait_for_selector("main, article, .project-detail", timeout=10000)
    except Exception:
        return None

    # Extract title
    title = ""
    title_el = await page.query_selector("h1, .project-title")
    if title_el:
        title = await title_el.inner_text()
    title = title.strip() or f"Projekt {external_id}"

    # Extract client/company
    client_name = None
    client_selectors = [
        ".company-name",
        "[data-label='Unternehmen']",
        ".client-name",
        "dt:has-text('Unternehmen') + dd",
        ".project-company"
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
        ".project-description",
        ".description",
        "[data-testid='description']",
        ".project-content",
        "article > p",
        ".details-text"
    ]
    for selector in desc_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                description = await el.inner_text()
                if len(description) > 50:  # Skip if too short
                    break
        except Exception:
            continue

    # Extract location
    location = None
    location_selectors = [
        ".location",
        "[data-label='Standort']",
        ".project-location",
        "dt:has-text('Standort') + dd",
        "dt:has-text('Einsatzort') + dd"
    ]
    for selector in location_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                location = await el.inner_text()
                break
        except Exception:
            continue

    # Extract hourly rate
    budget = None
    rate_selectors = [
        ".hourly-rate",
        "[data-label='Stundensatz']",
        "dt:has-text('Stundensatz') + dd",
        ".project-rate",
        ".rate"
    ]
    for selector in rate_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                budget = await el.inner_text()
                break
        except Exception:
            continue

    # Extract skills
    skills = []
    skill_selectors = [
        ".skills .tag, .skills .skill",
        ".project-skills span",
        "[data-testid='skill']",
        ".tag-list .tag"
    ]
    for selector in skill_selectors:
        try:
            els = await page.query_selector_all(selector)
            for el in els[:15]:  # Limit to 15 skills
                skill_text = await el.inner_text()
                if skill_text and len(skill_text) < 50:
                    skills.append(skill_text.strip())
            if skills:
                break
        except Exception:
            continue

    # Extract start date
    deadline = None
    date_selectors = [
        "dt:has-text('Start') + dd",
        "dt:has-text('Projektbeginn') + dd",
        ".start-date",
        "[data-label='Start']"
    ]
    for selector in date_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                date_text = await el.inner_text()
                # Try to parse German date format
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_text)
                if date_match:
                    deadline = datetime(
                        int(date_match.group(3)),
                        int(date_match.group(2)),
                        int(date_match.group(1))
                    )
                break
        except Exception:
            continue

    # Check if remote work mentioned
    page_text = await page.inner_text("body")
    remote_keywords = ["remote", "homeoffice", "home-office", "telearbeit", "100% remote"]
    remote = any(term in page_text.lower() for term in remote_keywords)

    return RawProject(
        source="freelancermap",
        external_id=external_id,
        url=url,
        title=title,
        client_name=client_name.strip() if client_name else None,
        description=description.strip() if description else None,
        skills=skills,
        budget=budget.strip() if budget else None,
        location=location.strip() if location else None,
        remote=remote,
        public_sector=False,
        deadline=deadline,
    )
