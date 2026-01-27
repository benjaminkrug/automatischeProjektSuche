"""Web scraping for client/company research."""

import asyncio
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus, urljoin

from playwright.async_api import Page

from app.core.logging import get_logger

logger = get_logger("sourcing.web.client")

# Rate limiting
WEB_REQUEST_DELAY_SECONDS = 5.0

# Max text lengths
MAX_ABOUT_TEXT_CHARS = 2000


@dataclass
class CompanyInfo:
    """Scraped company information."""
    website: Optional[str] = None
    about_text: Optional[str] = None
    hrb_number: Optional[str] = None
    founding_year: Optional[int] = None
    employee_count: Optional[str] = None
    kununu_rating: Optional[float] = None


async def find_company_website(
    page: Page,
    client_name: str,
    delay: float = WEB_REQUEST_DELAY_SECONDS,
) -> Optional[str]:
    """Find company website via DuckDuckGo search.

    Args:
        page: Playwright page
        client_name: Company name to search
        delay: Delay before request

    Returns:
        Company website URL, or None if not found
    """
    if not client_name or len(client_name) < 3:
        return None

    await asyncio.sleep(delay)

    try:
        # Use DuckDuckGo HTML search (no JavaScript required)
        search_query = quote_plus(f"{client_name} offizielle website")
        search_url = f"https://html.duckduckgo.com/html/?q={search_query}"

        logger.debug("Searching for company website: %s", client_name)

        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        # Find first result link
        results = await page.query_selector_all(".result__url")

        for result in results[:5]:
            try:
                href = await result.get_attribute("href")
                if not href:
                    url_text = await result.inner_text()
                    if url_text:
                        href = url_text.strip()

                if href:
                    # Clean up URL
                    if not href.startswith("http"):
                        href = "https://" + href.lstrip("/")

                    # Skip search engines, social media, etc.
                    skip_domains = [
                        "duckduckgo.com", "google.com", "bing.com",
                        "facebook.com", "linkedin.com", "twitter.com",
                        "xing.com", "wikipedia.org", "kununu.com",
                        "northdata.de", "firmenwissen.de",
                    ]

                    if not any(d in href.lower() for d in skip_domains):
                        logger.info("Found company website: %s", href[:80])
                        return href

            except Exception:
                continue

        logger.debug("No website found for: %s", client_name)
        return None

    except Exception as e:
        logger.warning("Error searching for company website: %s", e)
        return None


async def scrape_company_about(
    page: Page,
    url: str,
    delay: float = WEB_REQUEST_DELAY_SECONDS,
) -> Optional[str]:
    """Scrape "About Us" page from company website.

    Args:
        page: Playwright page
        url: Company website URL
        delay: Delay before request

    Returns:
        About text, or None if not found
    """
    if not url:
        return None

    await asyncio.sleep(delay)

    try:
        logger.debug("Scraping about page: %s", url[:60])

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Try to find "About Us" link
        about_patterns = [
            "a:has-text('Über uns')",
            "a:has-text('About')",
            "a:has-text('Unternehmen')",
            "a:has-text('Wir')",
            "a:has-text('Company')",
            "a[href*='about']",
            "a[href*='ueber']",
            "a[href*='unternehmen']",
        ]

        for pattern in about_patterns:
            try:
                link = await page.query_selector(pattern)
                if link:
                    href = await link.get_attribute("href")
                    if href:
                        about_url = urljoin(url, href)
                        await asyncio.sleep(2)  # Small delay before clicking
                        await page.goto(about_url, wait_until="domcontentloaded", timeout=30000)
                        break
            except Exception:
                continue

        # Extract main content
        content_selectors = [
            "main",
            "article",
            ".content",
            "#content",
            ".about",
            ".ueber-uns",
        ]

        text = ""
        for selector in content_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text and len(text) > 100:
                        break
            except Exception:
                continue

        # Fallback to body text
        if not text or len(text) < 100:
            try:
                text = await page.inner_text("body")
            except Exception:
                return None

        if text:
            # Clean and truncate
            text = _clean_text(text)
            if len(text) > MAX_ABOUT_TEXT_CHARS:
                text = text[:MAX_ABOUT_TEXT_CHARS] + "..."

            logger.info("Extracted about text: %d chars", len(text))
            return text

        return None

    except Exception as e:
        logger.warning("Error scraping about page: %s", e)
        return None


async def get_handelsregister_info(
    page: Page,
    client_name: str,
    delay: float = WEB_REQUEST_DELAY_SECONDS,
) -> dict:
    """Get company info from North Data (Handelsregister).

    Args:
        page: Playwright page
        client_name: Company name
        delay: Delay before request

    Returns:
        Dict with hrb_number, founding_year, employee_count
    """
    result = {
        "hrb_number": None,
        "founding_year": None,
        "employee_count": None,
    }

    if not client_name or len(client_name) < 3:
        return result

    await asyncio.sleep(delay)

    try:
        # Search on North Data (free tier, no login)
        search_query = quote_plus(client_name)
        search_url = f"https://www.northdata.de/search?q={search_query}"

        logger.debug("Searching North Data for: %s", client_name)

        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        # Click first result if available
        first_result = await page.query_selector(".company-list a.company")
        if first_result:
            await asyncio.sleep(2)
            await first_result.click()
            await page.wait_for_load_state("domcontentloaded")

            # Extract HRB number
            hrb_el = await page.query_selector(".register-number")
            if hrb_el:
                hrb_text = await hrb_el.inner_text()
                hrb_match = re.search(r"HRB\s*\d+", hrb_text)
                if hrb_match:
                    result["hrb_number"] = hrb_match.group()

            # Extract founding year
            page_text = await page.inner_text("body")

            # Look for "gegründet" or "Gründung"
            year_match = re.search(r"[Gg]egründet[:\s]+(\d{4})", page_text)
            if not year_match:
                year_match = re.search(r"[Gg]ründung[:\s]+(\d{4})", page_text)
            if year_match:
                result["founding_year"] = int(year_match.group(1))

            # Extract employee count
            emp_el = await page.query_selector(".employees, [data-label='Mitarbeiter']")
            if emp_el:
                result["employee_count"] = await emp_el.inner_text()
            else:
                emp_match = re.search(r"(\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?)\s*Mitarbeiter", page_text)
                if emp_match:
                    result["employee_count"] = emp_match.group(1) + " Mitarbeiter"

            logger.info(
                "North Data results: HRB=%s, Year=%s, Employees=%s",
                result["hrb_number"],
                result["founding_year"],
                result["employee_count"],
            )

    except Exception as e:
        logger.warning("Error fetching North Data: %s", e)

    return result


async def get_kununu_rating(
    page: Page,
    client_name: str,
    delay: float = WEB_REQUEST_DELAY_SECONDS,
) -> Optional[dict]:
    """Get employer rating from Kununu.

    Args:
        page: Playwright page
        client_name: Company name
        delay: Delay before request

    Returns:
        Dict with rating, or None if not found
    """
    if not client_name or len(client_name) < 3:
        return None

    await asyncio.sleep(delay)

    try:
        # Search on Kununu
        search_query = quote_plus(client_name)
        search_url = f"https://www.kununu.com/de/search?q={search_query}"

        logger.debug("Searching Kununu for: %s", client_name)

        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        # Handle cookie consent if present
        try:
            consent_btn = await page.query_selector(
                "button:has-text('Akzeptieren'), "
                "button:has-text('Alle akzeptieren')"
            )
            if consent_btn:
                await consent_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        # Find first company result
        result_link = await page.query_selector(".company-card a, .search-result a")
        if result_link:
            await asyncio.sleep(2)
            await result_link.click()
            await page.wait_for_load_state("domcontentloaded")

            # Extract rating
            rating_el = await page.query_selector(
                ".rating-value, "
                "[data-testid='rating'], "
                ".score"
            )
            if rating_el:
                rating_text = await rating_el.inner_text()
                # Parse rating (format: "3,8" or "3.8")
                rating_match = re.search(r"(\d)[,.](\d)", rating_text)
                if rating_match:
                    rating = float(f"{rating_match.group(1)}.{rating_match.group(2)}")
                    logger.info("Kununu rating for %s: %.1f", client_name, rating)
                    return {"rating": rating}

        logger.debug("No Kununu rating found for: %s", client_name)
        return None

    except Exception as e:
        logger.warning("Error fetching Kununu rating: %s", e)
        return None


def _clean_text(text: str) -> str:
    """Clean scraped text content."""
    if not text:
        return ""

    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text)

    # Remove common UI elements
    ui_patterns = [
        r"Cookie[s]? akzeptieren",
        r"Newsletter abonnieren",
        r"Folgen Sie uns",
        r"Share on",
        r"Teilen auf",
    ]
    for pattern in ui_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    return text.strip()


async def research_company(
    page: Page,
    client_name: str,
) -> CompanyInfo:
    """Complete company research workflow.

    Args:
        page: Playwright page
        client_name: Company name to research

    Returns:
        CompanyInfo with all scraped data
    """
    info = CompanyInfo()

    if not client_name:
        return info

    # Normalize company name (remove common suffixes)
    normalized_name = client_name.strip()
    for suffix in [" GmbH", " AG", " KG", " e.V.", " mbH", " & Co."]:
        if normalized_name.endswith(suffix):
            normalized_name = normalized_name[:-len(suffix)]

    logger.info("Researching company: %s", client_name)

    # 1. Find company website
    info.website = await find_company_website(page, normalized_name)

    # 2. Scrape about page
    if info.website:
        info.about_text = await scrape_company_about(page, info.website)

    # 3. Get Handelsregister info
    hr_info = await get_handelsregister_info(page, client_name)
    info.hrb_number = hr_info.get("hrb_number")
    info.founding_year = hr_info.get("founding_year")
    info.employee_count = hr_info.get("employee_count")

    # 4. Get Kununu rating
    kununu = await get_kununu_rating(page, client_name)
    if kununu:
        info.kununu_rating = kununu.get("rating")

    logger.info(
        "Research complete for %s: website=%s, hrb=%s, rating=%s",
        client_name,
        "yes" if info.website else "no",
        info.hrb_number or "n/a",
        info.kununu_rating or "n/a",
    )

    return info
