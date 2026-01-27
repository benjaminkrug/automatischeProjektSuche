"""HTML parsing for malt.de project pages."""

import re
from datetime import datetime
from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> list[dict]:
    """Parse malt.de search results page to extract project links."""
    results = []

    try:
        await page.wait_for_selector(
            ".project-card, .project-item, [data-project-id]",
            timeout=15000
        )
    except Exception:
        return results

    items = await page.query_selector_all(
        ".project-card, .project-item, "
        "[data-testid='project-card'], article"
    )

    for item in items:
        try:
            link = await item.query_selector(
                "a[href*='/project/'], a[href*='/projekte/'], "
                "a.project-title, h2 a, h3 a"
            )

            if not link:
                continue

            href = await link.get_attribute("href")
            title_text = await link.inner_text()

            if not href or not title_text:
                continue

            id_match = re.search(r"/project[s]?/([a-zA-Z0-9-]+)", href)
            if not id_match:
                id_match = re.search(r"[/-]([a-zA-Z0-9-]+)$", href)

            external_id = id_match.group(1) if id_match else href.split("/")[-1]

            if not href.startswith("http"):
                href = f"https://www.malt.de{href}"

            results.append({
                "external_id": external_id,
                "title": title_text.strip(),
                "url": href
            })

        except Exception:
            continue

    return results


async def parse_detail_page(page: Page, external_id: str, url: str) -> RawProject | None:
    """Parse malt.de project detail page to extract full information."""
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

    # Extract description
    description = ""
    desc_selectors = [
        ".project-description",
        ".description",
        "[data-testid='description']",
        ".project-content"
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

    # Extract budget
    budget = None
    rate_selectors = [
        ".budget",
        "[data-label='Budget']",
        ".project-budget",
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
        ".skills .tag",
        ".project-skills span",
        "[data-testid='skill']",
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

    # Check if remote work mentioned
    page_text = await page.inner_text("body")
    remote = any(term in page_text.lower() for term in ["remote", "homeoffice", "home-office"])

    return RawProject(
        source="malt",
        external_id=external_id,
        url=url,
        title=title,
        client_name=None,
        description=description.strip() if description else None,
        skills=skills,
        budget=budget.strip() if budget else None,
        location=None,
        remote=remote,
        public_sector=False,
    )
