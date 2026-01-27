"""HTML parsing for freelance.de project pages."""

import re
from datetime import datetime
from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> list[dict]:
    """Parse search results page to extract project links."""
    results = []

    # freelance.de uses Angular with dynamic loading
    try:
        # Wait for project links to appear
        await page.wait_for_selector(
            "a[href*='/projekt-']",
            timeout=15000
        )
    except Exception:
        return results

    # Give extra time for Angular to render
    await page.wait_for_timeout(3000)

    # freelance.de project links follow pattern: /projekte/projekt-<id>-<slug>
    links = await page.query_selector_all("a[href*='/projekt-']")

    for link in links:
        try:
            href = await link.get_attribute("href")
            if not href:
                continue

            # Only process actual project detail links
            if "/projekte/projekt-" not in href:
                continue

            title_text = await link.inner_text()
            if not title_text:
                continue

            # Clean title (remove extra whitespace, "Firmenname", etc.)
            title_clean = title_text.strip().replace("\n", " ")
            # Often titles contain "Firmenname" after actual title - extract just the job title
            if "Firmenname" in title_clean:
                title_clean = title_clean.split("Firmenname")[0].strip()

            # Skip very short titles (likely navigation)
            if len(title_clean) < 10:
                continue

            # Extract project ID from URL
            # Pattern: /projekte/projekt-1249923-DevOps-Engineer-m-w-d
            # Extract the numeric ID
            id_match = re.search(r"/projekt-(\d+)-", href)
            if id_match:
                external_id = id_match.group(1)
            else:
                # Fallback: use last path segment
                path_segment = href.rstrip("/").split("/")[-1]
                external_id = path_segment

            if not href.startswith("http"):
                href = f"https://www.freelance.de{href}"

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
    """Parse project detail page to extract full information."""
    try:
        await page.wait_for_selector("main, article, .content, h1", timeout=10000)
    except Exception:
        return None

    # Wait for dynamic content
    await page.wait_for_timeout(2000)

    # Extract title
    title = ""
    title_selectors = ["h1", ".project-title", "[class*='title']"]
    for selector in title_selectors:
        try:
            title_el = await page.query_selector(selector)
            if title_el:
                title = await title_el.inner_text()
                if title and len(title.strip()) > 5:
                    break
        except Exception:
            continue
    title = title.strip() or f"Projekt {external_id}"

    # Extract description - try multiple selectors
    description = ""
    desc_selectors = [
        ".project-description",
        "[class*='description']",
        "[class*='beschreibung']",
        ".project-content",
        ".aufgaben",
        "article p",
        "main p",
        ".content p"
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
        "[class*='location']",
        "[class*='standort']",
        "[class*='ort']",
        "[data-label='Standort']",
        "dt:has-text('Standort') + dd",
        "dt:has-text('Einsatzort') + dd",
        "*:has-text('Einsatzort') + *"
    ]
    for selector in location_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                location = await el.inner_text()
                if location and len(location.strip()) > 2:
                    break
        except Exception:
            continue

    # Extract budget/rate
    budget = None
    rate_selectors = [
        "[class*='budget']",
        "[class*='rate']",
        "[class*='stundensatz']",
        "[data-label='Budget']",
        "dt:has-text('Budget') + dd",
        "dt:has-text('Stundensatz') + dd",
        "*:has-text('Stundensatz') + *"
    ]
    for selector in rate_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                budget = await el.inner_text()
                if budget and len(budget.strip()) > 1:
                    break
        except Exception:
            continue

    # Extract skills
    skills = []
    skill_selectors = [
        ".skills .tag, .skills span",
        "[class*='skill']",
        "[class*='tag']",
        ".project-skills span",
        ".tag-list .tag"
    ]
    for selector in skill_selectors:
        try:
            els = await page.query_selector_all(selector)
            for el in els[:15]:
                skill_text = await el.inner_text()
                if skill_text and len(skill_text.strip()) < 50 and len(skill_text.strip()) > 1:
                    skills.append(skill_text.strip())
            if skills:
                break
        except Exception:
            continue

    # Check if remote work mentioned
    page_text = await page.inner_text("body")
    remote = any(term in page_text.lower() for term in ["remote", "homeoffice", "home-office", "100% remote"])

    return RawProject(
        source="freelance.de",
        external_id=external_id,
        url=url,
        title=title,
        client_name=None,
        description=description.strip() if description else None,
        skills=skills,
        budget=budget.strip() if budget else None,
        location=location.strip() if location else None,
        remote=remote,
        public_sector=False,
    )
