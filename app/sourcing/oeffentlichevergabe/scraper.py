"""Scraper for oeffentlichevergabe.de OpenData API.

The oeffentlichevergabe.de portal aggregates tenders from 600+ German
contracting authorities (Bund, Länder, Kommunen). The OpenData API
provides structured access to announcements.

API Docs: https://oeffentlichevergabe.de/documentation/swagger-ui/opendata/
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import httpx

from app.core.logging import get_logger
from app.sourcing.base import BaseScraper, RawProject, extract_cpv_codes
from app.sourcing.early_filter import should_skip_project

logger = get_logger("sourcing.oeffentlichevergabe")

# API endpoints - Note: The actual API structure may vary
# Primary: Try the documented OpenData API
# Fallback: Use the public search page
API_BASE = "https://www.oeffentlichevergabe.de/api"
ANNOUNCEMENTS_ENDPOINT = f"{API_BASE}/notices"

# Alternative endpoints to try
ALTERNATIVE_ENDPOINTS = [
    "https://www.oeffentlichevergabe.de/api/v1/notices",
    "https://www.oeffentlichevergabe.de/api/opendata/notices",
    "https://oeffentlichevergabe.de/api/notices",
]

# Default request settings
DEFAULT_TIMEOUT = 30.0
MAX_RESULTS_PER_PAGE = 100

# IT-relevant CPV code prefixes (72 = IT services, 48 = Software)
IT_CPV_PREFIXES = ["72", "48"]


@dataclass
class Announcement:
    """Parsed announcement from oeffentlichevergabe.de API."""

    announcement_id: str
    publication_date: datetime
    title: str
    description: str = ""
    contracting_authority: str = ""
    cpv_codes: List[str] = field(default_factory=list)
    submission_deadline: Optional[datetime] = None
    procedure_type: str = ""
    url: str = ""
    budget: Optional[float] = None
    location: str = ""

    def to_raw_project(self) -> RawProject:
        """Convert to RawProject for pipeline processing."""
        return RawProject(
            source="oeffentlichevergabe",
            external_id=self.announcement_id,
            url=self.url,
            title=self.title,
            client_name=self.contracting_authority,
            description=self.description,
            location=self.location,
            public_sector=True,
            project_type="tender",
            cpv_codes=self.cpv_codes,
            budget_max=int(self.budget) if self.budget else None,
            tender_deadline=self.submission_deadline,
            published_at=self.publication_date,
        )


class OeffentlichevergabeScraper(BaseScraper):
    """Scraper for oeffentlichevergabe.de OpenData API.

    Provides access to German public sector tenders from 600+ contracting
    authorities through the official OpenData REST API.
    """

    source_name = "oeffentlichevergabe"

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        """Initialize scraper.

        Args:
            timeout: Request timeout in seconds
        """
        self._timeout = timeout

    def is_public_sector(self) -> bool:
        """Always public sector."""
        return True

    async def scrape(self, max_pages: int = 3) -> List[RawProject]:
        """Scrape IT tenders from oeffentlichevergabe.de API.

        Tries multiple API endpoints until one works.

        Args:
            max_pages: Maximum number of result pages to fetch

        Returns:
            List of RawProject objects
        """
        projects = []

        # Build list of endpoints to try
        endpoints_to_try = [ANNOUNCEMENTS_ENDPOINT] + ALTERNATIVE_ENDPOINTS

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            working_endpoint = None

            # Find a working endpoint
            for endpoint in endpoints_to_try:
                try:
                    test_response = await client.get(
                        endpoint,
                        params={"page": 0, "size": 1},
                    )
                    if test_response.status_code < 400:
                        working_endpoint = endpoint
                        logger.debug("Found working endpoint: %s", endpoint)
                        break
                except Exception:
                    continue

            if not working_endpoint:
                logger.warning("oeffentlichevergabe.de: No working API endpoint found, skipping")
                return projects

            for page in range(max_pages):
                logger.debug("Fetching page %d from oeffentlichevergabe.de", page + 1)

                try:
                    announcements = await self._fetch_page(client, page, working_endpoint)

                    if not announcements:
                        logger.debug("No more results on page %d", page + 1)
                        break

                    for announcement in announcements:
                        # Convert to RawProject
                        project = announcement.to_raw_project()

                        # Apply early filter
                        if should_skip_project(project.title, project.description or ""):
                            logger.debug("Skipping (early filter): %s", project.title[:50])
                            continue

                        projects.append(project)

                except Exception as e:
                    logger.error("Error fetching page %d: %s", page + 1, e)
                    break

        logger.info("oeffentlichevergabe.de: found %d relevant tenders", len(projects))
        return projects

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        page: int,
        endpoint: str = None,
    ) -> List[Announcement]:
        """Fetch a single page of announcements.

        Args:
            client: HTTP client
            page: Page number (0-indexed)
            endpoint: API endpoint URL to use

        Returns:
            List of Announcement objects
        """
        endpoint = endpoint or ANNOUNCEMENTS_ENDPOINT

        # Build query parameters
        # Filter for IT-related CPV codes and recent publications
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        params = {
            "page": page,
            "size": MAX_RESULTS_PER_PAGE,
            "publicationDateFrom": date_from,
            "sortField": "publicationDate",
            "sortDirection": "DESC",
        }

        # Add CPV filter if supported
        # Note: API may use different parameter names
        cpv_filter = ",".join([f"{prefix}*" for prefix in IT_CPV_PREFIXES])
        params["cpvCode"] = cpv_filter

        try:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()

            data = response.json()
            return self._parse_response(data)

        except httpx.HTTPStatusError as e:
            # If CPV filter not supported, try without
            if e.response.status_code == 400:
                logger.warning("CPV filter not supported, fetching without filter")
                del params["cpvCode"]
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                data = response.json()
                return self._parse_response(data, filter_cpv=True)
            raise

    def _parse_response(
        self,
        data: Dict[str, Any],
        filter_cpv: bool = False,
    ) -> List[Announcement]:
        """Parse API response into Announcement objects.

        Args:
            data: Raw API response
            filter_cpv: Whether to filter for IT CPV codes locally

        Returns:
            List of Announcement objects
        """
        announcements = []

        # Handle various response structures
        items = data.get("content", data.get("items", data.get("announcements", [])))

        for item in items:
            announcement = self._parse_item(item)
            if not announcement:
                continue

            # Local CPV filtering if needed
            if filter_cpv:
                if not self._has_it_cpv(announcement.cpv_codes):
                    continue

            announcements.append(announcement)

        return announcements

    def _parse_item(self, item: Dict[str, Any]) -> Optional[Announcement]:
        """Parse a single announcement item.

        Args:
            item: Raw item from API response

        Returns:
            Announcement object or None
        """
        try:
            # Extract ID
            announcement_id = str(
                item.get("id") or
                item.get("announcementId") or
                item.get("noticeId", "")
            )

            if not announcement_id:
                return None

            # Parse dates
            pub_date_str = item.get("publicationDate", "")
            try:
                publication_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                publication_date = datetime.now()

            deadline_str = item.get("submissionDeadline") or item.get("tenderDeadline", "")
            submission_deadline = None
            if deadline_str:
                try:
                    submission_deadline = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            # Extract text fields
            title = item.get("title", "") or item.get("subject", "") or ""
            description = item.get("description", "") or item.get("shortDescription", "") or ""

            # Extract contracting authority
            authority = item.get("contractingAuthority", {})
            if isinstance(authority, dict):
                contracting_authority = authority.get("name", "") or authority.get("officialName", "")
            else:
                contracting_authority = str(authority) if authority else ""

            # Extract CPV codes
            cpv_raw = item.get("cpvCodes", item.get("cpv", []))
            if isinstance(cpv_raw, str):
                cpv_codes = extract_cpv_codes(cpv_raw)
            elif isinstance(cpv_raw, list):
                cpv_codes = []
                for c in cpv_raw:
                    if isinstance(c, dict):
                        code = c.get("code", "")
                    else:
                        code = str(c)
                    # Clean up code
                    code = re.sub(r"[^0-9]", "", code)[:8]
                    if code:
                        cpv_codes.append(code)
            else:
                # Try extracting from description
                cpv_codes = extract_cpv_codes(f"{title} {description}")

            # Extract budget
            budget = None
            budget_data = item.get("estimatedValue") or item.get("value") or item.get("budget")
            if budget_data:
                if isinstance(budget_data, dict):
                    budget = budget_data.get("amount") or budget_data.get("value")
                elif isinstance(budget_data, (int, float)):
                    budget = budget_data

            # Extract location
            location = ""
            loc_data = item.get("location") or item.get("placeOfPerformance", {})
            if isinstance(loc_data, dict):
                location = loc_data.get("city", "") or loc_data.get("region", "")
            elif isinstance(loc_data, str):
                location = loc_data

            # Build URL
            url = item.get("url") or item.get("link", "")
            if not url:
                url = f"https://oeffentlichevergabe.de/announcement/{announcement_id}"

            return Announcement(
                announcement_id=announcement_id,
                publication_date=publication_date,
                title=title,
                description=description,
                contracting_authority=contracting_authority,
                cpv_codes=cpv_codes,
                submission_deadline=submission_deadline,
                procedure_type=item.get("procedureType", ""),
                url=url,
                budget=float(budget) if budget else None,
                location=location,
            )

        except Exception as e:
            logger.warning("Failed to parse announcement: %s", e)
            return None

    def _has_it_cpv(self, cpv_codes: List[str]) -> bool:
        """Check if any CPV code indicates IT services.

        Args:
            cpv_codes: List of CPV codes

        Returns:
            True if any code starts with IT prefix
        """
        if not cpv_codes:
            return False

        for code in cpv_codes:
            for prefix in IT_CPV_PREFIXES:
                if code.startswith(prefix):
                    return True

        return False


async def run_oeffentlichevergabe_scraper(max_pages: int = 3) -> List[RawProject]:
    """Convenience function to run the scraper.

    Args:
        max_pages: Maximum pages to fetch

    Returns:
        List of RawProject objects
    """
    scraper = OeffentlichevergabeScraper()
    return await scraper.scrape(max_pages=max_pages)
