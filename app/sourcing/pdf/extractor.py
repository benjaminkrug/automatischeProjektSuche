"""PDF download and text extraction for tender documents."""

import asyncio
import io
import re
from typing import Optional

import pdfplumber
from playwright.async_api import Page

from app.core.logging import get_logger

logger = get_logger("sourcing.pdf")

# Constants for limits
MAX_PDF_PAGES = 50
MAX_PDF_TEXT_CHARS = 10000
MAX_COMBINED_TEXT_CHARS = 30000
PDF_DOWNLOAD_DELAY_SECONDS = 7.0
PAGE_REQUEST_DELAY_SECONDS = 3.0

# Keywords for identifying relevant PDFs
RELEVANT_PDF_KEYWORDS = [
    "leistungsverzeichnis",
    "vergabeunterlagen",
    "leistungsbeschreibung",
    "anforderungskatalog",
    "pflichtenheft",
    "lastenheft",
    "technische spezifikation",
    "ausschreibungsunterlagen",
    "lv",
    "lvb",
]


async def download_pdf(
    page: Page,
    url: str,
    delay: float = PDF_DOWNLOAD_DELAY_SECONDS,
    timeout_ms: int = 60000,
) -> Optional[bytes]:
    """Download a PDF file from URL with rate limiting.

    Args:
        page: Playwright page for making requests
        url: URL of the PDF file
        delay: Delay before download (rate limiting)
        timeout_ms: Download timeout in milliseconds

    Returns:
        PDF content as bytes, or None if download failed
    """
    logger.debug("Waiting %.1fs before PDF download: %s", delay, url[:80])
    await asyncio.sleep(delay)

    try:
        # Use page.request for downloading to maintain session/cookies
        response = await page.request.get(url, timeout=timeout_ms)

        if response.status != 200:
            logger.warning(
                "PDF download failed with status %d: %s",
                response.status,
                url[:80],
            )
            return None

        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            logger.warning("Response is not PDF (content-type: %s): %s", content_type, url[:80])
            return None

        body = await response.body()
        logger.info("Downloaded PDF: %d bytes from %s", len(body), url[:60])
        return body

    except asyncio.TimeoutError:
        logger.warning("PDF download timeout: %s", url[:80])
        return None
    except Exception as e:
        logger.warning("PDF download error: %s - %s", type(e).__name__, url[:80])
        return None


def extract_pdf_text(
    pdf_bytes: bytes,
    max_pages: int = MAX_PDF_PAGES,
    max_chars: int = MAX_PDF_TEXT_CHARS,
) -> tuple[str, bool]:
    """Extract text content from PDF bytes.

    Args:
        pdf_bytes: Raw PDF content
        max_pages: Maximum pages to process (for cost control)
        max_chars: Maximum characters to extract

    Returns:
        Tuple of (extracted_text, was_truncated)
    """
    was_truncated = False
    text_parts = []
    total_chars = 0

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_pages = len(pdf.pages)

            if total_pages > max_pages:
                logger.warning(
                    "PDF has %d pages, processing only first %d",
                    total_pages,
                    max_pages,
                )
                was_truncated = True

            pages_to_process = min(total_pages, max_pages)

            for i, page in enumerate(pdf.pages[:pages_to_process]):
                try:
                    page_text = page.extract_text() or ""

                    # Check character limit
                    if total_chars + len(page_text) > max_chars:
                        remaining = max_chars - total_chars
                        if remaining > 0:
                            text_parts.append(page_text[:remaining])
                        was_truncated = True
                        logger.debug(
                            "PDF text truncated at page %d/%d (char limit)",
                            i + 1,
                            pages_to_process,
                        )
                        break

                    text_parts.append(page_text)
                    total_chars += len(page_text)

                except Exception as e:
                    logger.debug("Error extracting page %d: %s", i + 1, e)
                    continue

            extracted_text = "\n\n".join(text_parts)
            logger.debug(
                "Extracted %d chars from %d/%d pages",
                len(extracted_text),
                min(pages_to_process, len(text_parts)),
                total_pages,
            )
            return extracted_text, was_truncated

    except Exception as e:
        logger.warning("PDF extraction failed: %s", e)
        return "", False


async def identify_relevant_pdfs(
    page: Page,
    max_pdfs: int = 3,
) -> list[dict]:
    """Find relevant PDF links on a tender detail page.

    Prioritizes PDFs with keywords like "Leistungsverzeichnis",
    "Vergabeunterlagen", etc.

    Args:
        page: Playwright page with tender detail loaded
        max_pdfs: Maximum PDFs to return

    Returns:
        List of dicts with 'url' and 'title' keys
    """
    pdf_links = []

    try:
        # Find all PDF links
        selectors = [
            "a[href$='.pdf']",
            "a[href*='download'][href*='pdf']",
            "a[href*='/document']",
            "a[href*='/file']",
        ]

        for selector in selectors:
            links = await page.query_selector_all(selector)
            for link in links:
                try:
                    href = await link.get_attribute("href")
                    if not href:
                        continue

                    # Build full URL if relative
                    if href.startswith("/"):
                        base_url = page.url.split("/")[0:3]
                        href = "/".join(base_url) + href
                    elif not href.startswith("http"):
                        continue

                    # Get link text for relevance scoring
                    text = await link.inner_text()
                    text = (text or "").strip().lower()

                    # Also check parent element text
                    parent = await link.evaluate("el => el.parentElement?.innerText || ''")
                    parent_text = (parent or "").strip().lower()

                    combined_text = f"{text} {parent_text}"

                    # Skip duplicates
                    if any(p["url"] == href for p in pdf_links):
                        continue

                    pdf_links.append({
                        "url": href,
                        "title": text[:100] if text else "",
                        "context": combined_text[:200],
                    })

                except Exception:
                    continue

    except Exception as e:
        logger.debug("Error finding PDF links: %s", e)

    # Score and sort by relevance
    def relevance_score(pdf: dict) -> int:
        score = 0
        context = pdf.get("context", "").lower()
        for keyword in RELEVANT_PDF_KEYWORDS:
            if keyword in context:
                score += 10
        return score

    pdf_links.sort(key=relevance_score, reverse=True)

    # Return top N with highest relevance
    result = pdf_links[:max_pdfs]
    logger.debug("Found %d PDFs, returning top %d", len(pdf_links), len(result))
    return result


def combine_project_text(
    html_desc: str,
    pdf_texts: list[str],
    max_chars: int = MAX_COMBINED_TEXT_CHARS,
) -> str:
    """Combine HTML description with PDF texts for embedding.

    Args:
        html_desc: HTML description from tender page
        pdf_texts: List of extracted PDF texts
        max_chars: Maximum total characters

    Returns:
        Combined text for embedding generation
    """
    parts = []

    # Add HTML description first (most important)
    if html_desc:
        parts.append("=== PROJEKTBESCHREIBUNG ===\n" + html_desc.strip())

    # Add PDF texts
    for i, pdf_text in enumerate(pdf_texts):
        if pdf_text:
            parts.append(f"=== PDF-DOKUMENT {i + 1} ===\n" + pdf_text.strip())

    combined = "\n\n".join(parts)

    # Truncate if necessary
    if len(combined) > max_chars:
        combined = combined[:max_chars]
        logger.debug("Combined text truncated to %d chars", max_chars)

    return combined


def log_large_pdf_warning(
    project_id: str,
    pdf_url: str,
    page_count: int,
    processed_pages: int,
) -> None:
    """Log warning for large PDFs that were truncated.

    Args:
        project_id: External project ID for reference
        pdf_url: URL of the large PDF
        page_count: Total pages in PDF
        processed_pages: Number of pages actually processed
    """
    logger.warning(
        "Large PDF truncated | project=%s | pages=%d/%d | url=%s",
        project_id,
        processed_pages,
        page_count,
        pdf_url[:100],
    )


def normalize_pdf_text(text: str) -> str:
    """Clean and normalize extracted PDF text.

    Args:
        text: Raw extracted text

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text)

    # Remove page numbers and headers/footers (common patterns)
    text = re.sub(r"Seite \d+ von \d+", "", text)
    text = re.sub(r"Page \d+ of \d+", "", text)

    # Remove very short lines (often headers/footers)
    lines = text.split("\n")
    lines = [l.strip() for l in lines if len(l.strip()) > 5]
    text = "\n".join(lines)

    return text.strip()
