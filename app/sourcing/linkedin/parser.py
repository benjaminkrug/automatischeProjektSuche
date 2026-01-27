"""HTML parsing for LinkedIn job pages."""

import re
from datetime import datetime
from playwright.async_api import Page

from app.sourcing.base import RawProject


async def parse_search_results(page: Page) -> list[dict]:
    """Parse LinkedIn search results page to extract job data.

    Note: We extract as much data as possible from search results
    to minimize detail page requests (anti-scraping protection).
    """
    results = []

    try:
        await page.wait_for_selector(
            ".jobs-search__results-list li, .job-card-container, [data-job-id]",
            timeout=15000
        )
    except Exception:
        return results

    items = await page.query_selector_all(
        ".jobs-search__results-list li, .job-card-container, "
        "[data-job-id], .job-result-card"
    )

    for item in items:
        try:
            # Extract job ID
            job_id = await item.get_attribute("data-job-id")
            if not job_id:
                # Try to extract from link
                link = await item.query_selector("a[href*='/jobs/view/']")
                if link:
                    href = await link.get_attribute("href")
                    id_match = re.search(r"/jobs/view/(\d+)", href)
                    job_id = id_match.group(1) if id_match else None

            if not job_id:
                continue

            # Extract title
            title_el = await item.query_selector(
                ".job-card-list__title, .base-search-card__title, "
                "h3, h4, a.job-title"
            )
            if not title_el:
                continue

            title = await title_el.inner_text()
            if not title:
                continue

            # Build job URL
            url = f"https://www.linkedin.com/jobs/view/{job_id}/"

            # Extract company name
            company = None
            company_el = await item.query_selector(
                ".job-card-container__company-name, "
                ".base-search-card__subtitle, "
                ".job-card-list__company-name"
            )
            if company_el:
                company = await company_el.inner_text()

            # Extract location
            location = None
            location_el = await item.query_selector(
                ".job-card-container__metadata-item, "
                ".job-search-card__location, "
                ".job-card-list__location"
            )
            if location_el:
                location = await location_el.inner_text()

            # Extract description snippet
            description = None
            desc_el = await item.query_selector(
                ".job-card-list__description, "
                ".job-search-card__snippet, "
                ".job-description"
            )
            if desc_el:
                description = await desc_el.inner_text()

            # Check for remote
            item_text = await item.inner_text()
            remote = any(term in item_text.lower() for term in ["remote", "homeoffice", "hybrid"])

            results.append({
                "external_id": job_id,
                "title": title.strip(),
                "url": url,
                "company": company.strip() if company else None,
                "location": location.strip() if location else None,
                "description": description.strip() if description else None,
                "remote": remote,
            })

        except Exception:
            continue

    return results


async def parse_detail_page(page: Page, external_id: str, url: str) -> RawProject | None:
    """Parse LinkedIn job detail page to extract full information.

    Note: Due to anti-scraping protection, we primarily rely on search results data.
    """
    try:
        await page.wait_for_selector("main, article, .job-view-layout", timeout=10000)
    except Exception:
        return None

    # Extract title
    title = ""
    title_el = await page.query_selector("h1, .job-title, .topcard__title")
    if title_el:
        title = await title_el.inner_text()
    title = title.strip() or f"Job {external_id}"

    # Extract company name
    client_name = None
    company_el = await page.query_selector(
        ".company-name, .topcard__org-name-link, "
        "[data-test='employer-name']"
    )
    if company_el:
        client_name = await company_el.inner_text()

    # Extract description
    description = ""
    desc_selectors = [
        ".job-description",
        ".show-more-less-html__markup",
        ".description__text"
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
    location_el = await page.query_selector(
        ".topcard__flavor--bullet, .job-location, "
        "[data-test='job-location']"
    )
    if location_el:
        location = await location_el.inner_text()

    # Check for remote
    page_text = await page.inner_text("body")
    remote = any(term in page_text.lower() for term in ["remote", "homeoffice", "hybrid"])

    return RawProject(
        source="linkedin",
        external_id=external_id,
        url=url,
        title=title,
        client_name=client_name.strip() if client_name else None,
        description=description.strip() if description else None,
        skills=[],
        budget=None,
        location=location.strip() if location else None,
        remote=remote,
        public_sector=False,
    )
