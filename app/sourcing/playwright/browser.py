"""Browser management for Playwright scraping."""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from playwright.async_api import async_playwright, Browser, Page, Playwright

from app.core.logging import get_logger
from app.settings import settings

logger = get_logger("sourcing.browser")


def _setup_windows_event_loop():
    """Setup proper event loop policy for Windows.

    Windows requires ProactorEventLoop for subprocess support,
    but Playwright needs special handling in some contexts.
    """
    if sys.platform == "win32":
        # Use ProactorEventLoop for subprocess support on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class BrowserManager:
    """Manages Playwright browser instance."""

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def start(self) -> None:
        """Start Playwright and launch browser."""
        logger.debug("Starting browser...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        logger.debug("Browser started")

    async def stop(self) -> None:
        """Close browser and stop Playwright."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.debug("Browser stopped")

    async def new_page(self) -> Page:
        """Create new browser page with default settings."""
        if not self._browser:
            await self.start()

        context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="de-DE",
            timezone_id="Europe/Berlin",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        return page

    @asynccontextmanager
    async def page_context(self) -> AsyncGenerator[Page, None]:
        """Context manager for page lifecycle."""
        page = await self.new_page()
        try:
            yield page
        finally:
            await page.context.close()


# Global browser manager instance (lazy initialization)
_browser_manager: Optional[BrowserManager] = None


def get_browser_manager() -> BrowserManager:
    """Get or create global browser manager.

    Returns:
        BrowserManager instance
    """
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager


def reset_browser_manager() -> None:
    """Reset the global browser manager (useful for testing)."""
    global _browser_manager
    _browser_manager = None


@asynccontextmanager
async def browser_session() -> AsyncGenerator[BrowserManager, None]:
    """Context manager for browser session lifecycle.

    Usage:
        async with browser_session() as manager:
            async with manager.page_context() as page:
                await page.goto(url)
    """
    # Setup Windows event loop policy if needed
    _setup_windows_event_loop()

    manager = get_browser_manager()
    try:
        await manager.start()
        yield manager
    finally:
        await manager.stop()
