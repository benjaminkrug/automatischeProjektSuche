"""Scraper for service.bund.de RSS feed (Ausschreibungen)."""

from typing import List

import feedparser

from app.core.logging import get_logger
from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.early_filter import should_skip_project
from app.sourcing.bund_rss.parser import parse_rss_entry

logger = get_logger("sourcing.bund_rss")

# RSS Feed URL for Ausschreibungen
RSS_FEED_URL = "https://www.service.bund.de/Content/Globals/Functions/RSSFeed/RSSGenerator_Ausschreibungen.xml"

# Limit entries per run
MAX_ENTRIES_PER_RUN = 50


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

    async def scrape(self, max_pages: int = 1) -> List[RawProject]:
        """Fetch and parse RSS feed.

        Args:
            max_pages: Ignored for RSS (single feed)

        Returns:
            List of RawProject objects
        """
        projects = []

        logger.info("Fetching RSS feed from %s", RSS_FEED_URL)

        try:
            feed = feedparser.parse(RSS_FEED_URL)
        except Exception as e:
            logger.error("Error fetching RSS feed: %s", e)
            return projects

        if feed.bozo and feed.bozo_exception:
            logger.warning("RSS feed parsing issue: %s", feed.bozo_exception)

        if not feed.entries:
            logger.warning("No entries in RSS feed")
            return projects

        logger.info("RSS feed contains %d entries", len(feed.entries))

        # Process entries
        for i, entry in enumerate(feed.entries[:MAX_ENTRIES_PER_RUN]):
            try:
                project = parse_rss_entry(entry)

                if not project:
                    continue

                # Apply early filter
                if should_skip_project(project.title, project.description or ""):
                    logger.debug("Skipping (early filter): %s", project.title[:50])
                    continue

                projects.append(project)
                logger.debug(
                    "Parsed entry %d: %s",
                    i + 1,
                    project.title[:50],
                )

            except Exception as e:
                logger.warning("Error parsing entry %d: %s", i, e)
                continue

        logger.info("Parsed %d IT-relevant projects from RSS feed", len(projects))
        return projects


async def run_bund_rss_scraper() -> List[RawProject]:
    """Convenience function to run bund_rss scraper.

    Returns:
        List of scraped projects
    """
    scraper = BundRssScraper()
    return await scraper.scrape()
