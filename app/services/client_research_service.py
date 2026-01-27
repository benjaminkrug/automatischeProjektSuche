"""Client research service with caching."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import ClientResearchCache
from app.sourcing.web.client_scraper import CompanyInfo, research_company
from app.sourcing.playwright.browser import get_browser_manager

logger = get_logger("services.client_research")

# Cache TTL (30 days)
CACHE_TTL_DAYS = 30


@dataclass
class ClientResearch:
    """Client research result."""
    client_name: str
    website: Optional[str] = None
    about_text: Optional[str] = None
    hrb_number: Optional[str] = None
    founding_year: Optional[int] = None
    employee_count: Optional[str] = None
    kununu_rating: Optional[float] = None
    from_cache: bool = False


def normalize_client_name(name: str) -> str:
    """Normalize client name for cache lookup.

    Args:
        name: Original client name

    Returns:
        Normalized name (lowercase, trimmed, common suffixes removed)
    """
    if not name:
        return ""

    # Lowercase and strip
    normalized = name.lower().strip()

    # Remove common legal suffixes
    suffixes = [
        " gmbh", " ag", " kg", " e.v.", " mbh", " & co.",
        " ohg", " gbr", " ug", " se", " kgaa",
    ]
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]

    # Remove extra whitespace
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def get_cached_research(
    db: Session,
    client_name: str,
) -> Optional[ClientResearch]:
    """Get cached client research if still valid.

    Args:
        db: Database session
        client_name: Client name to look up

    Returns:
        ClientResearch if cached and valid, None otherwise
    """
    normalized = normalize_client_name(client_name)
    if not normalized:
        return None

    cache_entry = (
        db.query(ClientResearchCache)
        .filter(ClientResearchCache.client_name_normalized == normalized)
        .first()
    )

    if not cache_entry:
        return None

    # Check TTL
    if cache_entry.last_updated:
        expiry = cache_entry.last_updated + timedelta(days=CACHE_TTL_DAYS)
        if datetime.utcnow() > expiry:
            logger.debug("Cache expired for: %s", client_name)
            return None

    logger.debug("Cache hit for: %s", client_name)

    return ClientResearch(
        client_name=client_name,
        website=cache_entry.company_website,
        about_text=cache_entry.company_about_text,
        hrb_number=cache_entry.hrb_number,
        founding_year=cache_entry.founding_year,
        employee_count=cache_entry.employee_count,
        kununu_rating=cache_entry.kununu_rating,
        from_cache=True,
    )


def save_to_cache(
    db: Session,
    client_name: str,
    info: CompanyInfo,
) -> None:
    """Save research results to cache.

    Args:
        db: Database session
        client_name: Original client name
        info: Scraped company info
    """
    normalized = normalize_client_name(client_name)
    if not normalized:
        return

    # Check if entry exists
    cache_entry = (
        db.query(ClientResearchCache)
        .filter(ClientResearchCache.client_name_normalized == normalized)
        .first()
    )

    if cache_entry:
        # Update existing entry
        cache_entry.company_website = info.website
        cache_entry.company_about_text = info.about_text
        cache_entry.hrb_number = info.hrb_number
        cache_entry.founding_year = info.founding_year
        cache_entry.employee_count = info.employee_count
        cache_entry.kununu_rating = info.kununu_rating
        cache_entry.last_updated = datetime.utcnow()
    else:
        # Create new entry
        cache_entry = ClientResearchCache(
            client_name_normalized=normalized,
            company_website=info.website,
            company_about_text=info.about_text,
            hrb_number=info.hrb_number,
            founding_year=info.founding_year,
            employee_count=info.employee_count,
            kununu_rating=info.kununu_rating,
            last_updated=datetime.utcnow(),
        )
        db.add(cache_entry)

    db.commit()
    logger.debug("Cached research for: %s", client_name)


async def get_client_research(
    db: Session,
    client_name: str,
    skip_cache: bool = False,
) -> ClientResearch:
    """Get client research, using cache or scraping.

    Args:
        db: Database session
        client_name: Client name to research
        skip_cache: If True, always fetch fresh data

    Returns:
        ClientResearch with available data
    """
    if not client_name:
        return ClientResearch(client_name="")

    # Check cache first
    if not skip_cache:
        cached = get_cached_research(db, client_name)
        if cached:
            return cached

    logger.info("Fetching fresh research for: %s", client_name)

    # Scrape fresh data
    browser_manager = get_browser_manager()

    try:
        async with browser_manager.page_context() as page:
            info = await research_company(page, client_name)

            # Save to cache
            save_to_cache(db, client_name, info)

            return ClientResearch(
                client_name=client_name,
                website=info.website,
                about_text=info.about_text,
                hrb_number=info.hrb_number,
                founding_year=info.founding_year,
                employee_count=info.employee_count,
                kununu_rating=info.kununu_rating,
                from_cache=False,
            )

    except Exception as e:
        logger.warning("Error researching client %s: %s", client_name, e)

        # Return empty result on error
        return ClientResearch(
            client_name=client_name,
            from_cache=False,
        )


def get_client_research_sync(
    db: Session,
    client_name: str,
    skip_cache: bool = False,
) -> ClientResearch:
    """Synchronous wrapper for get_client_research.

    Args:
        db: Database session
        client_name: Client name to research
        skip_cache: If True, always fetch fresh data

    Returns:
        ClientResearch with available data
    """
    import asyncio

    # Check cache first (avoid async for cache hits)
    if not skip_cache:
        cached = get_cached_research(db, client_name)
        if cached:
            return cached

    # Run async version
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                get_client_research(db, client_name, skip_cache=True),
            )
            return future.result()
    else:
        return asyncio.run(
            get_client_research(db, client_name, skip_cache=True)
        )
