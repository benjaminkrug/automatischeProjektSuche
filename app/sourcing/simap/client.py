"""HTTP client for simap.ch API."""

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from app.core.logging import get_logger

logger = get_logger("sourcing.simap.client")


class SimapApiClient:
    """Client for simap.ch public procurement API.

    The simap.ch API provides access to Swiss public procurement tenders.
    It supports searching by CPV codes (Common Procurement Vocabulary).
    """

    BASE_URL = "https://www.simap.ch/api/publications/v2"
    SEARCH_ENDPOINT = "/project/project-search"

    # IT-related CPV codes
    DEFAULT_CPV_CODES = [
        "72000000",  # IT services
        "72200000",  # Software programming and consultancy
        "72400000",  # Internet services
        "72500000",  # Computer-related services
    ]

    def __init__(
        self,
        timeout: float = 30.0,
        rate_limit_delay: float = 1.0,
    ):
        """Initialize the API client.

        Args:
            timeout: Request timeout in seconds
            rate_limit_delay: Delay between requests in seconds
        """
        self._timeout = timeout
        self._rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0

    async def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        import time

        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit_delay:
            await asyncio.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    async def search_projects(
        self,
        cpv_codes: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search for projects using the simap.ch API.

        Args:
            cpv_codes: List of CPV codes to filter by (defaults to IT codes)
            limit: Maximum number of results per request (max 50)
            offset: Pagination offset

        Returns:
            API response as dictionary

        Raises:
            httpx.HTTPError: On HTTP request failure
        """
        await self._rate_limit()

        if cpv_codes is None:
            cpv_codes = self.DEFAULT_CPV_CODES

        payload = {
            "cpvCodes": cpv_codes,
            "orderAddressCountryOnlySwitzerland": True,
            "limit": min(limit, 50),
            "offset": offset,
        }

        url = f"{self.BASE_URL}{self.SEARCH_ENDPOINT}"

        logger.debug("Requesting %s with offset=%d", url, offset)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            )
            response.raise_for_status()
            return response.json()

    async def fetch_all_pages(
        self,
        cpv_codes: Optional[List[str]] = None,
        max_pages: int = 5,
        page_size: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch multiple pages of search results.

        Args:
            cpv_codes: List of CPV codes to filter by
            max_pages: Maximum number of pages to fetch
            page_size: Number of results per page

        Returns:
            List of all project items from all pages
        """
        all_projects = []

        for page in range(max_pages):
            offset = page * page_size

            try:
                response = await self.search_projects(
                    cpv_codes=cpv_codes,
                    limit=page_size,
                    offset=offset,
                )
            except httpx.HTTPError as e:
                logger.error("HTTP error fetching page %d: %s", page + 1, e)
                break

            # Extract projects from response
            projects = response.get("projects", [])
            if not projects:
                logger.debug("No more projects at offset %d", offset)
                break

            all_projects.extend(projects)
            logger.debug(
                "Page %d: fetched %d projects (total: %d)",
                page + 1,
                len(projects),
                len(all_projects),
            )

            # Check if we've reached the end
            total = response.get("total", 0)
            if offset + len(projects) >= total:
                break

        return all_projects
