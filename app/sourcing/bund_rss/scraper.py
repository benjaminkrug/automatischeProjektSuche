"""Scraper for service.bund.de RSS feed (Ausschreibungen).

Supports multiple IT-keyword-filtered RSS feeds for better coverage
of relevant software/IT tenders.
"""

from typing import List, Set

import feedparser

from app.core.logging import get_logger
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.bund_rss.parser import parse_rss_entry

logger = get_logger("sourcing.bund_rss")

# Base RSS Feed URL (all tenders)
RSS_FEED_BASE = "https://www.service.bund.de/Content/Globals/Functions/RSSFeed/RSSGenerator_Ausschreibungen.xml"

# IT-keyword-filtered RSS Feed URLs
# service.bund.de allows search parameter 'q' in RSS URL
RSS_FEED_URLS = [
    # Base feed (all tenders)
    RSS_FEED_BASE,
    # IT-specific keyword feeds
    f"{RSS_FEED_BASE}?q=Software",
    f"{RSS_FEED_BASE}?q=IT-Entwicklung",
    f"{RSS_FEED_BASE}?q=Webanwendung",
    f"{RSS_FEED_BASE}?q=Softwareentwicklung",
    f"{RSS_FEED_BASE}?q=Programmierung",
    f"{RSS_FEED_BASE}?q=Webportal",
    f"{RSS_FEED_BASE}?q=Digitalisierung",
    f"{RSS_FEED_BASE}?q=IT-Dienstleistung",
]

# Limit entries per feed
MAX_ENTRIES_PER_FEED = 30

# Total limit across all feeds
MAX_ENTRIES_TOTAL = 100


class BundRssScraper(BaseScraper):
    """Scraper for service.bund.de RSS feed.

    This scraper fetches the RSS feed of public sector tenders from
    service.bund.de. It complements the bund.de Playwright scraper
    by providing a lighter-weight way to monitor new tenders.

    Note: The RSS feed contains different/additional data than the
    main bund.de search, so both sources should be used.
    """

    source_name = "bund_rss"

    def is_public_sector(self) -> bool:
        return True

    @property
    def FEED_URLS(self) -> List[str]:
        """Get list of RSS feed URLs.

        Returns:
            List of RSS feed URLs including keyword-filtered feeds
        """
        return RSS_FEED_URLS

    async def scrape(self, max_pages: int = 1) -> List[RawProject]:
        """Fetch and parse multiple RSS feeds.

        Fetches both the base feed and IT-keyword-filtered feeds
        for better coverage of relevant tenders.

        Args:
            max_pages: Number of keyword feeds to include (1 = base only)

        Returns:
            List of RawProject objects
        """
        projects = []
        seen_ids: Set[str] = set()  # Deduplicate across feeds

        # Determine which feeds to use
        feeds_to_use = RSS_FEED_URLS[:max_pages] if max_pages > 0 else RSS_FEED_URLS

        for feed_url in feeds_to_use:
            logger.debug("Fetching RSS feed from %s", feed_url)

            try:
                feed = feedparser.parse(feed_url)
            except Exception as e:
                logger.warning("Error fetching RSS feed %s: %s", feed_url, e)
                continue

            if feed.bozo and feed.bozo_exception:
                logger.debug("RSS feed parsing issue: %s", feed.bozo_exception)

            if not feed.entries:
                logger.debug("No entries in RSS feed: %s", feed_url)
                continue

            entries_added = 0

            for entry in feed.entries[:MAX_ENTRIES_PER_FEED]:
                try:
                    project = parse_rss_entry(entry)

                    if not project:
                        continue

                    # Skip duplicates (same tender in multiple keyword feeds)
                    if project.external_id in seen_ids:
                        continue
                    seen_ids.add(project.external_id)

                    # Apply early filter
                    if should_skip_project(project.title, project.description or ""):
                        logger.debug("Skipping (early filter): %s", project.title[:50])
                        continue

                    projects.append(project)
                    entries_added += 1

                    # Stop if total limit reached
                    if len(projects) >= MAX_ENTRIES_TOTAL:
                        break

                except Exception as e:
                    logger.debug("Error parsing entry: %s", e)
                    continue

            logger.debug("Added %d projects from feed: %s", entries_added, feed_url.split("?")[-1][:30])

            # Stop if total limit reached
            if len(projects) >= MAX_ENTRIES_TOTAL:
                break

        logger.info(
            "Parsed %d unique projects from %d RSS feeds",
            len(projects),
            len(feeds_to_use),
        )
        return projects


async def run_bund_rss_scraper() -> List[RawProject]:
    """Convenience function to run bund_rss scraper.

    Returns:
        List of scraped projects
    """
    scraper = BundRssScraper()
    return await scraper.scrape()
