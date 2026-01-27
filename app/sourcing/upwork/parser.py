"""HTML parsing for Upwork.com job pages."""

import re
from datetime import datetime
from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> list[dict]:
    """Parse Upwork search results page to extract job data.

    Note: We extract as much data as possible from search results
    to minimize detail page requests (anti-bot protection).
    """
    results = []

    try:
        await page.wait_for_selector(
            "[data-test='job-tile'], .job-tile, .oJobTile",
            timeout=15000
        )
    except Exception:
        return results

    items = await page.query_selector_all(
        "[data-test='job-tile'], .job-tile, .oJobTile, "
        "[data-testid='job-tile'], article[class*='job']"
    )

    for item in items:
        try:
            # Extract title and link
            link = await item.query_selector(
                "a[href*='/jobs/'], a[href*='/job/'], "
                "a.job-title-link, h2 a, h3 a"
            )

            if not link:
                continue

            href = await link.get_attribute("href")
            title_text = await link.inner_text()

            if not href or not title_text:
                continue

            # Extract job ID from URL
            id_match = re.search(r"/jobs?/[~]?([a-zA-Z0-9]+)", href)
            if not id_match:
                id_match = re.search(r"[/-]([a-zA-Z0-9]+)(?:\?|$)", href)

            external_id = id_match.group(1) if id_match else href.split("/")[-1].split("?")[0]

            if not href.startswith("http"):
                href = f"https://www.upwork.com{href}"

            # Extract description from search results
            description = ""
            desc_el = await item.query_selector(
                "[data-test='job-description'], .job-description, "
                ".oJobTileDescription, p"
            )
            if desc_el:
                description = await desc_el.inner_text()

            # Extract budget
            budget = None
            budget_el = await item.query_selector(
                "[data-test='budget'], .job-budget, "
                ".oJobTileBudget, .budget"
            )
            if budget_el:
                budget = await budget_el.inner_text()

            # Extract skills
            skills = []
            skill_els = await item.query_selector_all(
                "[data-test='skill'], .skill-badge, "
                ".oJobTileSkill, .skill-tag"
            )
            for el in skill_els[:10]:
                skill_text = await el.inner_text()
                if skill_text and len(skill_text) < 50:
                    skills.append(skill_text.strip())

            results.append({
                "external_id": external_id,
                "title": title_text.strip(),
                "url": href,
                "description": description.strip() if description else None,
                "budget": budget.strip() if budget else None,
                "skills": skills,
            })

        except Exception:
            continue

    return results


async def parse_detail_page(page: Page, external_id: str, url: str) -> RawProject | None:
    """Parse Upwork job detail page to extract full information.

    Note: Due to anti-bot protection, we primarily rely on search results data.
    """
    try:
        await page.wait_for_selector("main, article, .job-details", timeout=10000)
    except Exception:
        return None

    # Extract title
    title = ""
    title_el = await page.query_selector("h1, .job-title")
    if title_el:
        title = await title_el.inner_text()
    title = title.strip() or f"Job {external_id}"

    # Extract description
    description = ""
    desc_selectors = [
        ".job-description",
        "[data-test='description']",
        ".description"
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
    budget_selectors = [
        "[data-test='budget']",
        ".job-budget",
        ".budget"
    ]
    for selector in budget_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                budget = await el.inner_text()
                break
        except Exception:
            continue

    # Extract skills
    skills = []
    skill_els = await page.query_selector_all(
        "[data-test='skill'], .skill-badge, .skill-tag"
    )
    for el in skill_els[:15]:
        try:
            skill_text = await el.inner_text()
            if skill_text and len(skill_text) < 50:
                skills.append(skill_text.strip())
        except Exception:
            continue

    return RawProject(
        source="upwork",
        external_id=external_id,
        url=url,
        title=title,
        client_name=None,
        description=description.strip() if description else None,
        skills=skills,
        budget=budget.strip() if budget else None,
        location=None,
        remote=True,  # Upwork jobs are typically remote
        public_sector=False,
    )
