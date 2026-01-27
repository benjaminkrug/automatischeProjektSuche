"""Web scraping module for client research."""

from app.sourcing.web.client_scraper import (
    find_company_website,
    scrape_company_about,
    get_handelsregister_info,
    get_kununu_rating,
)

__all__ = [
    "find_company_website",
    "scrape_company_about",
    "get_handelsregister_info",
    "get_kununu_rating",
]
