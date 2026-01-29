"""TED API v3 Client for EU public procurement tenders.

Provides structured access to TED (Tenders Electronic Daily) via the
official REST API v3, replacing fragile HTML scraping.

API Docs: https://api.ted.europa.eu/docs
         https://ted.europa.eu/api/swagger-ui/index.html

Note: The TED API v3 uses POST requests with JSON body for search.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import httpx

from app.core.logging import get_logger
from app.sourcing.base import RawProject

logger = get_logger("sourcing.ted.api")

# TED API v3 endpoints
# The search API uses POST with JSON body
TED_API_BASE = "https://api.ted.europa.eu/v3"
TED_SEARCH_ENDPOINT = f"{TED_API_BASE}/notices/search"

# Default timeout for API requests
DEFAULT_TIMEOUT = 30.0

# IT-relevant CPV codes (72xxx = IT services, 48xxx = Software packages)
IT_CPV_CODES = [
    # 72xxx - IT-Dienstleistungen
    "72000000",  # IT services
    "72200000",  # Software programming
    "72210000",  # Programming services
    "72211000",  # Programming of systems and user software
    "72212000",  # Programming of application software
    "72220000",  # Systems and technical consultancy
    "72230000",  # Custom software development
    "72240000",  # Systems analysis and programming
    "72250000",  # Systems and support services
    "72260000",  # Software-related services
    "72262000",  # Software development
    "72263000",  # Software implementation
    "72267000",  # Software maintenance and repair
    "72268000",  # Software supply
    # 72xxx - Web/Internet-spezifisch (NEU)
    "72400000",  # Internet services
    "72413000",  # Website design
    "72420000",  # Internet development services
    "72421000",  # Internet/Intranet client application development
    "72422000",  # Internet/Intranet server application development
    # 48xxx - Softwarepakete und Informationssysteme
    "48000000",  # Software package and information systems
    "48200000",  # Networking, Internet and intranet software
    "48220000",  # Internet software package
    "48400000",  # Business transaction software
    "48500000",  # Communication and multimedia software
    "48600000",  # Database and operating software
    "48800000",  # Information systems and servers
    "48810000",  # Information systems
]


@dataclass
class TedNotice:
    """Structured tender notice from TED API."""

    notice_id: str
    publication_date: datetime
    title: str
    description: str = ""
    contracting_authority: str = ""
    country: str = ""
    cpv_codes: List[str] = field(default_factory=list)
    budget_value: Optional[float] = None
    budget_currency: str = "EUR"
    submission_deadline: Optional[datetime] = None
    notice_type: str = ""
    procedure_type: str = ""
    url: str = ""

    def to_raw_project(self) -> RawProject:
        """Convert to RawProject for pipeline processing."""
        return RawProject(
            source="ted",
            external_id=self.notice_id,
            url=self.url or f"https://ted.europa.eu/udl?uri=TED:NOTICE:{self.notice_id}:TEXT:DE:HTML",
            title=self.title,
            client_name=self.contracting_authority,
            description=self.description,
            public_sector=True,
            project_type="tender",
            cpv_codes=self.cpv_codes,
            budget_max=int(self.budget_value) if self.budget_value else None,
            tender_deadline=self.submission_deadline,
            published_at=self.publication_date,
        )


class TedApiClient:
    """Client for TED REST API v3.

    Provides methods to search and retrieve EU public procurement notices
    with structured data extraction.
    """

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        """Initialize API client.

        Args:
            timeout: Request timeout in seconds
        """
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # Map ISO alpha-2 to alpha-3 country codes
    COUNTRY_MAP = {
        "DE": "DEU", "AT": "AUT", "CH": "CHE", "NL": "NLD", "BE": "BEL",
        "FR": "FRA", "IT": "ITA", "ES": "ESP", "PL": "POL", "CZ": "CZE",
    }

    async def search_it_tenders(
        self,
        country: str = "DE",
        days_back: int = 30,
        max_results: int = 100,
    ) -> List[TedNotice]:
        """Search for IT-related tenders.

        Args:
            country: Country code (ISO 3166-1 alpha-2 or alpha-3)
            days_back: Number of days to look back from today
            max_results: Maximum number of results to return

        Returns:
            List of TedNotice objects
        """
        # Convert alpha-2 to alpha-3 if needed
        country_code = self.COUNTRY_MAP.get(country.upper(), country.upper())

        # Date filter in YYYYMMDD format
        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")

        # Build search query body for POST request
        # TED API v3 uses semantic field names and ISO alpha-3 country codes
        search_body = {
            "query": f"classification-cpv=72* AND buyer-country={country_code} AND dispatch-date>={date_from}",
            "fields": [
                "publication-number",
                "notice-type",
                "title-proc",
                "description-proc",
                "buyer-name",
                "buyer-country",
                "classification-cpv",
                "dispatch-date",
                "deadline-receipt-tender-date-lot",
                "estimated-value-proc",
                "estimated-value-lot",
            ],
            "limit": min(max_results, 250),
            "page": 1,
        }

        logger.debug("TED API search body: %s", search_body)

        try:
            if not self._client:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    return await self._execute_search(client, search_body)
            return await self._execute_search(self._client, search_body)
        except Exception as e:
            logger.error("TED API search failed: %s", e)
            return []

    async def _execute_search(
        self,
        client: httpx.AsyncClient,
        search_body: Dict[str, Any],
    ) -> List[TedNotice]:
        """Execute search request and parse results.

        Args:
            client: HTTP client
            search_body: Search request body (JSON)

        Returns:
            List of parsed TedNotice objects
        """
        notices = []

        # Use the main TED API v3 search endpoint
        endpoints = [
            (TED_SEARCH_ENDPOINT, "POST"),
        ]

        for endpoint, method in endpoints:
            try:
                if method == "POST":
                    response = await client.post(
                        endpoint,
                        json=search_body,
                        headers={"Content-Type": "application/json"},
                    )
                else:
                    # GET fallback with query params
                    params = {
                        "q": search_body.get("query", "PC=[72*]"),
                        "pageSize": search_body.get("pageSize", 50),
                        "pageNum": search_body.get("pageNum", 1),
                    }
                    response = await client.get(endpoint, params=params)

                response.raise_for_status()
                data = response.json()

                # Handle various response structures
                results = (
                    data.get("notices") or
                    data.get("results") or
                    data.get("items") or
                    data.get("content") or
                    []
                )

                logger.info("TED API (%s) returned %d results", endpoint.split("/")[-1], len(results))

                for item in results:
                    notice = self._parse_notice(item)
                    if notice:
                        notices.append(notice)

                # If we got results, don't try other endpoints
                if notices:
                    break

            except httpx.HTTPStatusError as e:
                logger.debug("TED endpoint %s failed: %s", endpoint, e.response.status_code)
                continue
            except Exception as e:
                logger.debug("TED endpoint %s error: %s", endpoint, e)
                continue

        if not notices:
            logger.warning("All TED API endpoints failed, falling back to Playwright")

        return notices

    def _extract_localized_text(self, data: Any, prefer_lang: str = "deu") -> str:
        """Extract text from localized field (dict with language codes).

        Args:
            data: Localized field data (dict, list, or string)
            prefer_lang: Preferred language code (lowercase)

        Returns:
            Extracted text string
        """
        if not data:
            return ""
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            # Try preferred language first, then English, then any available
            text = data.get(prefer_lang) or data.get("eng") or data.get("deu")
            if not text and data:
                text = next(iter(data.values()), "")
            # Handle nested lists
            if isinstance(text, list) and text:
                text = text[0]
            return str(text) if text else ""
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                return self._extract_localized_text(first, prefer_lang)
            return str(first)
        return ""

    def _parse_datetime(self, date_str: Any) -> Optional[datetime]:
        """Parse datetime from various formats.

        Args:
            date_str: Date string or list of date strings

        Returns:
            Parsed datetime or None
        """
        if not date_str:
            return None
        # Handle list of dates (take first)
        if isinstance(date_str, list):
            date_str = date_str[0] if date_str else None
        if not date_str or not isinstance(date_str, str):
            return None
        try:
            # Handle formats: YYYYMMDD, YYYY-MM-DD, ISO with timezone
            if len(date_str) == 8 and date_str.isdigit():
                return datetime.strptime(date_str, "%Y%m%d")
            # Remove timezone suffix like "+01:00" for simple parsing
            clean_str = date_str.split("+")[0].split("Z")[0]
            if "T" in clean_str:
                return datetime.fromisoformat(clean_str)
            return datetime.strptime(clean_str[:10], "%Y-%m-%d")
        except (ValueError, AttributeError):
            return None

    def _parse_notice(self, data: Dict[str, Any]) -> Optional[TedNotice]:
        """Parse API response item into TedNotice.

        Handles TED API v3 response format with semantic field names:
        - publication-number: notice ID
        - title-proc: procedure title (localized)
        - description-proc: description (localized)
        - buyer-name: contracting authority (localized)
        - buyer-country: country code (array)
        - classification-cpv: CPV codes (array)
        - dispatch-date: publication date
        - deadline-receipt-tender-date-lot: submission deadline (array)
        - estimated-value-proc: budget value

        Args:
            data: Raw API response item

        Returns:
            Parsed TedNotice or None if parsing fails
        """
        try:
            # Extract notice ID
            notice_id = data.get("publication-number") or data.get("ND") or ""
            if not notice_id:
                return None

            # Parse publication/dispatch date
            publication_date = (
                self._parse_datetime(data.get("dispatch-date")) or
                self._parse_datetime(data.get("publication-date")) or
                self._parse_datetime(data.get("PD")) or
                datetime.now()
            )

            # Extract title (prefer title-proc, then notice-title)
            title = (
                self._extract_localized_text(data.get("title-proc")) or
                self._extract_localized_text(data.get("notice-title")) or
                self._extract_localized_text(data.get("title-lot")) or
                self._extract_localized_text(data.get("TI"))
            )

            # Extract description
            description = (
                self._extract_localized_text(data.get("description-proc")) or
                self._extract_localized_text(data.get("description-lot")) or
                self._extract_localized_text(data.get("description"))
            )

            # Extract contracting authority
            contracting_authority = self._extract_localized_text(data.get("buyer-name"))

            # Extract CPV codes
            cpv_raw = data.get("classification-cpv") or data.get("PC") or []
            cpv_codes = []
            if isinstance(cpv_raw, str):
                cpv_codes = [c.strip()[:8] for c in cpv_raw.split(",") if c.strip()]
            elif isinstance(cpv_raw, list):
                for c in cpv_raw:
                    code = str(c.get("code") if isinstance(c, dict) else c)
                    if code:
                        cpv_codes.append(code[:8])

            # Extract budget value
            budget_value = None
            budget_currency = "EUR"
            for field in ["estimated-value-proc", "estimated-value-lot", "VA", "total-value"]:
                budget_raw = data.get(field)
                if budget_raw:
                    if isinstance(budget_raw, (int, float)):
                        budget_value = float(budget_raw)
                        break
                    elif isinstance(budget_raw, dict):
                        budget_value = budget_raw.get("amount") or budget_raw.get("value")
                        budget_currency = budget_raw.get("currency", "EUR")
                        if budget_value:
                            break
                    elif isinstance(budget_raw, str):
                        match = re.search(r"(\d+(?:[.,]\d+)?)", budget_raw.replace(" ", ""))
                        if match:
                            budget_value = float(match.group(1).replace(",", "."))
                            break

            # Extract submission deadline
            submission_deadline = (
                self._parse_datetime(data.get("deadline-receipt-tender-date-lot")) or
                self._parse_datetime(data.get("DD"))
            )

            # Extract country
            country_raw = data.get("buyer-country") or data.get("CO") or data.get("CY") or ""
            if isinstance(country_raw, list):
                country = country_raw[0] if country_raw else ""
            else:
                country = str(country_raw)

            # Build URL from links or construct default
            links = data.get("links", {})
            html_links = links.get("html", {}) if isinstance(links, dict) else {}
            url = html_links.get("DEU") or html_links.get("ENG") or ""
            if not url and notice_id:
                url = f"https://ted.europa.eu/de/notice/-/detail/{notice_id}"

            # Skip if no title
            if not title:
                return None

            return TedNotice(
                notice_id=str(notice_id),
                publication_date=publication_date,
                title=title,
                description=description,
                contracting_authority=contracting_authority,
                country=country,
                cpv_codes=cpv_codes,
                budget_value=float(budget_value) if budget_value else None,
                budget_currency=budget_currency,
                submission_deadline=submission_deadline,
                notice_type=data.get("notice-type") or data.get("TD") or "",
                procedure_type=data.get("procedure-type") or data.get("PR") or "",
                url=url,
            )

        except Exception as e:
            logger.warning("Failed to parse TED notice: %s - data: %s", e, str(data)[:200])
            return None

    async def get_notice_details(self, notice_id: str) -> Optional[TedNotice]:
        """Get detailed information for a specific notice.

        Args:
            notice_id: TED notice ID

        Returns:
            TedNotice with full details or None
        """
        endpoint = f"{TED_API_BASE}/notices/{notice_id}"

        try:
            if not self._client:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(endpoint)
            else:
                response = await self._client.get(endpoint)

            response.raise_for_status()
            data = response.json()
            return self._parse_notice(data)

        except Exception as e:
            logger.warning("Failed to get TED notice %s: %s", notice_id, e)
            return None


async def search_ted_tenders(
    country: str = "DE",
    days_back: int = 30,
    max_results: int = 100,
) -> List[RawProject]:
    """Convenience function to search TED and return RawProject list.

    Args:
        country: Country code
        days_back: Days to look back
        max_results: Max results

    Returns:
        List of RawProject objects
    """
    async with TedApiClient() as client:
        notices = await client.search_it_tenders(
            country=country,
            days_back=days_back,
            max_results=max_results,
        )
        return [notice.to_raw_project() for notice in notices]
