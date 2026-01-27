"""HTML parsing for gulp.de project pages."""

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

    # Wait for results to load (GULP uses dynamic loading)
    try:
        await page.wait_for_selector(
            "a[href*='/projekte/agentur'], a[href*='/projekte/talentfinder']",
            timeout=15000
        )
    except Exception:
        return results

    # Give extra time for dynamic content to render
    await page.wait_for_timeout(2000)

    # GULP Strategy: Find project links directly
    # GULP uses these patterns for individual projects:
    # - /gulp2/g/projekte/agentur/<id>
    # - /gulp2/g/projekte/talentfinder/<id>
    links = await page.query_selector_all(
        "a[href*='/projekte/agentur/'], "
        "a[href*='/projekte/talentfinder/']"
    )

    for link in links:
        try:
            href = await link.get_attribute("href")
            if not href:
                continue

            title_text = await link.inner_text()
            if not title_text:
                continue

            # Skip very short titles (likely navigation elements)
            title_clean = title_text.strip().replace("\n", " ")
            if len(title_clean) < 10:
                continue

            # Skip common navigation text
            skip_texts = ["projekt", "mehr", "weiter", "details", "ansehen", "erfahren"]
            if title_clean.lower() in skip_texts:
                continue

            # Extract external ID from URL
            # Pattern: /gulp2/g/projekte/agentur/C01231361 -> C01231361
            path_parts = href.rstrip("/").split("/")
            external_id = path_parts[-1] if path_parts else href

            # Build full URL if needed
            if not href.startswith("http"):
                href = f"https://www.gulp.de{href}"

            # Avoid duplicates
            if any(r["external_id"] == external_id for r in results):
                continue

            results.append({
                "external_id": external_id,
                "title": title_clean,
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
    title_el = await page.query_selector("h1, .project-title, [data-testid='project-title']")
    if title_el:
        title = await title_el.inner_text()
    title = title.strip() or f"Projekt {external_id}"

    # Extract company name
    client_name = None
    client_selectors = [
        ".company-name",
        "[data-label='Unternehmen']",
        ".client-info",
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
        ".details-section p",
        ".aufgaben"
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

    # Extract location
    location = None
    location_selectors = [
        ".location",
        "[data-label='Standort']",
        ".project-location",
        "dt:has-text('Standort') + dd",
        "dt:has-text('Einsatzort') + dd",
        ".einsatzort"
    ]
    for selector in location_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                location = await el.inner_text()
                break
        except Exception:
            continue

    # Extract daily rate (GULP typically shows daily rates)
    budget = None
    rate_selectors = [
        ".daily-rate",
        "[data-label='Tagessatz']",
        "dt:has-text('Tagessatz') + dd",
        ".project-rate",
        ".rate",
        ".honorar"
    ]
    for selector in rate_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                budget = await el.inner_text()
                break
        except Exception:
            continue

    # Extract technologies/skills
    skills = []
    skill_selectors = [
        ".technologies .tag",
        ".skills .skill",
        ".project-skills span",
        "[data-testid='skill']",
        ".technologien span",
        ".tag-list .tag"
    ]
    for selector in skill_selectors:
        try:
            els = await page.query_selector_all(selector)
            for el in els[:15]:
                skill_text = await el.inner_text()
                if skill_text and len(skill_text) < 50:
                    skills.append(skill_text.strip())
            if skills:
                break
        except Exception:
            continue

    # Extract project start date
    deadline = None
    date_selectors = [
        "dt:has-text('Projektstart') + dd",
        "dt:has-text('Start') + dd",
        ".start-date",
        "[data-label='Projektstart']"
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
        source="gulp",
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
