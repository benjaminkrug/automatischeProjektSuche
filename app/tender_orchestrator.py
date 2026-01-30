"""Tender Orchestrator - Public sector tender acquisition pipeline.

Separate pipeline for public tenders (Ausschreibungen) with specialized
scoring for agency projects (Web/Mobile Apps, 50k-250k EUR).

Flow:
1. Scrape → Only public sector portals
2. CPV Pre-Filter → Filter by relevant CPV codes
3. Dedupe → As usual
4. Lot Extraction → Split large tenders into individual lots
5. Budget Parsing → Extract total budget (not hourly rate)
6. PDF Analysis → Analyze procurement documents
7. Tech Filter → Web/Mobile Apps detection
8. Procedure Scoring → Prefer negotiation procedures
9. Eligibility Check → References, revenue, certifications
10. Scoring → Specialized weighting
11. Output → Review queue (no auto-documents)
"""

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.constants import (
    SEPARATOR_LINE,
    SEPARATOR_LINE_THIN,
    PROJECT_STATUS_REJECTED,
    PROJECT_STATUS_REVIEW,
)
from app.core.logging import setup_logging, get_logger
from app.db.models import (
    Project,
    TenderLot,
    TenderDecision,
    RejectionReason,
    ReviewQueue,
)
from app.db.session import SessionLocal
from app.settings import settings
from app.sourcing.cpv_filter import passes_cpv_filter, CpvFilterResult
from app.sourcing.tender_filter import (
    score_tender,
    TenderScore,
    detect_procedure_type,
    check_eligibility,
    extract_budget_from_text,
)
from app.sourcing.pdf_analyzer import TenderPdfAnalyzer
from app.sourcing.client_db import (
    get_or_create_client,
    get_client_for_project,
    increment_tender_seen,
)
from app.sourcing.normalize import save_projects, filter_old_projects, record_scraper_run
from app.sourcing.client_enrichment import (
    enrich_client,
    get_client_score_modifier,
)
from app.sourcing.dedup import dedupe_incoming_projects
from app.sourcing.metrics import update_metrics_after_scoring
from app.ai.tender_classifier import (
    classify_tender,
    quick_software_check,
    get_classification_score_modifier,
    enrich_project_with_classification,
)
from app.sourcing.playwright.browser import browser_session
from app.sourcing.base import extract_cpv_codes
from app.notifications.email import send_tender_notification

logger = get_logger("tender_orchestrator")


def _run_async(coro):
    """Run async coroutine with proper event loop handling for Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


# Public sector portal list (Phase 2 erweitert)
TENDER_PORTALS = [
    "bund.de",
    "bund_rss",
    "dtvp",
    "evergabe",
    "evergabe_online",
    "simap",
    "ted",
    # Phase 2: Neue Portale
    "oeffentlichevergabe",
    "nrw",
    "bayern",
    "bawue",
]


@dataclass
class TenderPipelineStats:
    """Statistics for a tender pipeline run."""

    scraped: int = 0
    cpv_filtered: int = 0
    cpv_passed: int = 0
    new_projects: int = 0
    lots_extracted: int = 0
    analyzed: int = 0
    high_priority: int = 0
    review_queue: int = 0
    rejected: int = 0
    skipped: int = 0
    errors: int = 0

    def log_summary(self) -> None:
        """Log summary statistics."""
        logger.info(SEPARATOR_LINE)
        logger.info("TENDER-STATISTIK")
        logger.info(SEPARATOR_LINE)
        logger.info("  Gescraped:        %d", self.scraped)
        logger.info("  CPV gefiltert:    %d (-> %d durchgelassen)", self.cpv_filtered, self.cpv_passed)
        logger.info("  Neue Projekte:    %d", self.new_projects)
        logger.info("  Lose extrahiert:  %d", self.lots_extracted)
        logger.info("  Analysiert:       %d", self.analyzed)
        logger.info("  Hohe Priorität:   %d", self.high_priority)
        logger.info("  Review-Queue:     %d", self.review_queue)
        logger.info("  Abgelehnt:        %d", self.rejected)
        logger.info("  Übersprungen:     %d", self.skipped)
        logger.info("  Fehler:           %d", self.errors)
        logger.info(SEPARATOR_LINE)


class TenderOrchestrator:
    """Orchestrates the tender acquisition pipeline."""

    def __init__(self):
        """Initialize orchestrator."""
        self._db: Optional[Session] = None
        self._stats = TenderPipelineStats()
        self._high_priority_tenders: List[dict] = []

    @property
    def db(self) -> Session:
        """Get database session (lazy initialization)."""
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def run(self) -> TenderPipelineStats:
        """Execute the complete tender pipeline.

        Returns:
            TenderPipelineStats with run statistics
        """
        logger.info(SEPARATOR_LINE)
        logger.info(
            "Tender-Bot Run - %s",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        logger.info(SEPARATOR_LINE)

        try:
            # 1. Check capacity
            if not self._check_capacity():
                logger.info("Kapazität erschöpft - Pipeline beendet")
                self._stats.log_summary()
                return self._stats

            # 2. Scrape public sector portals
            raw_projects = _run_async(self._scrape_tender_portals())

            # 3. CPV Pre-Filter
            cpv_filtered = self._apply_cpv_filter(raw_projects)

            # 4. Dedupe and save
            new_projects = self._save_and_dedupe(cpv_filtered)

            # 4b. Also get existing 'new' status tenders for re-analysis
            pending_projects = self._get_pending_tenders()
            if pending_projects:
                logger.info(
                    "Zusätzlich %d bestehende Tenders mit Status 'new' zur Analyse",
                    len(pending_projects),
                )

            # Combine new + pending (unique by ID)
            all_to_process = list(new_projects)
            processed_ids = {p.id for p in all_to_process}
            for p in pending_projects:
                if p.id not in processed_ids:
                    all_to_process.append(p)
                    processed_ids.add(p.id)

            if not all_to_process:
                logger.info("Keine Ausschreibungen zu analysieren.")
                self._stats.log_summary()
                return self._stats

            logger.info("Insgesamt %d Ausschreibungen zu analysieren", len(all_to_process))

            # 5-11. Process each project
            for project in all_to_process:
                self._process_tender(project)

            # Send email notification for high-priority tenders
            if self._high_priority_tenders:
                send_tender_notification(self._high_priority_tenders)

            # Log summary
            self._stats.log_summary()
            return self._stats

        except Exception as e:
            logger.error("Fehler in Tender-Pipeline: %s", e)
            self._stats.errors += 1
            raise

        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._db is not None:
            self._db.close()
            self._db = None

    def _check_capacity(self) -> bool:
        """Check if we have capacity for new tender applications."""
        active_count = self._get_active_tender_count()
        if active_count >= settings.max_active_tenders:
            logger.info(
                "Tender-Kapazität erschöpft (%d/%d)",
                active_count,
                settings.max_active_tenders,
            )
            return False
        logger.info(
            "Tender-Kapazität: %d/%d",
            active_count,
            settings.max_active_tenders,
        )
        return True

    def _get_active_tender_count(self) -> int:
        """Get count of active tender applications."""
        return (
            self.db.query(Project)
            .filter(
                Project.project_type == "tender",
                Project.status.in_(["applied", "review"]),
            )
            .count()
        )

    def _get_pending_tenders(self) -> List[Project]:
        """Get existing tenders with status 'new' for re-analysis.

        This allows re-processing tenders that were previously rejected
        but need to be re-scored (e.g., after scoring logic changes).
        """
        return (
            self.db.query(Project)
            .filter(
                Project.project_type == "tender",
                Project.status == "new",
            )
            .all()
        )

    async def _scrape_tender_portals(self) -> List:
        """Scrape all public sector portals."""
        logger.info("Phase 1: Scraping Tender-Portale")
        logger.info(SEPARATOR_LINE_THIN)

        all_projects = []

        # Import scrapers
        from app.sourcing.bund.scraper import BundScraper
        from app.sourcing.bund_rss.scraper import BundRssScraper
        from app.sourcing.dtvp.scraper import DtvpScraper
        from app.sourcing.evergabe.scraper import EvergabeScraper
        from app.sourcing.evergabe_online.scraper import EvergabeOnlineScraper
        from app.sourcing.simap.scraper import SimapScraper
        from app.sourcing.ted.scraper import TedScraper
        # Phase 2: Neue Scraper
        from app.sourcing.oeffentlichevergabe.scraper import OeffentlichevergabeScraper
        from app.sourcing.nrw.scraper import NrwScraper
        from app.sourcing.bayern.scraper import BayernScraper
        from app.sourcing.bawue.scraper import BawueScraper

        scrapers = [
            ("bund.de", BundScraper()),
            ("bund_rss", BundRssScraper()),
            ("dtvp", DtvpScraper()),
            ("evergabe", EvergabeScraper()),
            ("evergabe_online", EvergabeOnlineScraper()),
            ("simap.ch", SimapScraper()),
            ("ted", TedScraper()),
            # Phase 2: Neue Portale
            ("oeffentlichevergabe", OeffentlichevergabeScraper()),
            ("nrw", NrwScraper()),
            ("bayern", BayernScraper()),
            ("bawue", BawueScraper()),
        ]

        async with browser_session():
            for portal_name, scraper in scrapers:
                if not scraper.is_enabled:
                    logger.info("[%s] Deaktiviert - übersprungen", portal_name)
                    continue

                logger.info("[%s]", portal_name)
                try:
                    projects = await scraper.scrape(max_pages=settings.scraper_max_pages)
                    scraped_count = len(projects)

                    # Filter old projects (published before last run)
                    projects, filtered_old = filter_old_projects(self.db, projects, portal_name)

                    # Mark as tender projects
                    for p in projects:
                        p.project_type = "tender"

                    all_projects.extend(projects)
                    self._stats.scraped += scraped_count

                    logger.info(
                        "  Gefunden: %d, nach Datumsfilter: %d Ausschreibungen",
                        scraped_count,
                        len(projects),
                    )

                    # Record successful run
                    record_scraper_run(
                        self.db,
                        portal=portal_name,
                        projects_found=scraped_count,
                        new_projects=len(projects),
                        filtered_old=filtered_old,
                    )

                except Exception as e:
                    logger.error("  Fehler beim Scraping von %s: %s", portal_name, e)
                    self._stats.errors += 1
                    # Record failed run
                    record_scraper_run(
                        self.db,
                        portal=portal_name,
                        status="error",
                        error_details=str(e),
                    )

        logger.info("Gesamt gescraped: %d Ausschreibungen", self._stats.scraped)
        return all_projects

    def _apply_cpv_filter(self, raw_projects: List) -> List:
        """Apply CPV code pre-filter."""
        logger.info("Phase 2: CPV-Code Pre-Filter")
        logger.info(SEPARATOR_LINE_THIN)

        filtered = []
        for project in raw_projects:
            cpv_codes = getattr(project, "cpv_codes", []) or []
            result: CpvFilterResult = passes_cpv_filter(cpv_codes)

            self._stats.cpv_filtered += 1

            if result.passes:
                # Store CPV bonus for later scoring (as attribute)
                project._cpv_bonus = result.bonus_score
                filtered.append(project)
                self._stats.cpv_passed += 1

                if result.relevant_codes:
                    title = getattr(project, "title", "")[:50]
                    logger.debug("  CPV pass: %s: %s", title, result.reason)
            else:
                title = getattr(project, "title", "")[:50]
                logger.debug("  CPV skip: %s: %s", title, result.reason)

        logger.info(
            "CPV-Filter: %d von %d durchgelassen",
            self._stats.cpv_passed,
            self._stats.cpv_filtered,
        )
        return filtered

    def _save_and_dedupe(self, raw_projects: List) -> List[Project]:
        """Save projects after deduplication."""
        logger.info("Phase 3: Deduplizierung")
        logger.info(SEPARATOR_LINE_THIN)

        saved = save_projects(self.db, raw_projects)
        self._stats.new_projects = len(saved)

        logger.info("Neue Ausschreibungen nach Dedupe: %d", len(saved))
        return saved

    def _process_tender(self, project: Project) -> None:
        """Process a single tender through the pipeline."""
        logger.info(SEPARATOR_LINE)
        logger.info("Ausschreibung: %s...", project.title[:60])
        logger.info("Quelle: %s | ID: %s", project.source, project.external_id)
        logger.info(SEPARATOR_LINE)

        try:
            # Mark as tender
            project.project_type = "tender"

            # Extract CPV codes from text if not already populated
            if not project.cpv_codes:
                combined_text = f"{project.title or ''} {project.description or ''} {project.pdf_text or ''}"
                extracted_cpv = extract_cpv_codes(combined_text)
                if extracted_cpv:
                    project.cpv_codes = extracted_cpv
                    logger.info("  CPV-Codes extrahiert: %s", ", ".join(extracted_cpv[:5]))

            # Get or create client
            client, client_data = self._process_client(project)

            # Analyze PDFs if available
            self._analyze_pdfs(project)

            # Extract lots if applicable
            lots = self._extract_lots(project)

            if lots:
                # Process each lot separately
                for lot in lots:
                    self._process_lot(project, lot, client_data)
            else:
                # Process as single tender
                self._score_and_decide(project, client_data)

            self._stats.analyzed += 1

        except Exception as e:
            logger.error("Fehler bei Verarbeitung: %s", e)
            self._stats.errors += 1
            project.status = "error"
            self.db.commit()

    def _analyze_pdfs(self, project: Project) -> None:
        """Analyze PDF documents attached to the project."""
        pdf_urls = getattr(project, "pdf_urls", None)
        if not pdf_urls and not project.pdf_text:
            return

        # If we already have pdf_text from scraping, try to extract budget
        if project.pdf_text and not project.budget_max:
            budget = extract_budget_from_text(project.pdf_text)
            if budget:
                project.budget_max = budget
                logger.info("  Budget aus PDF extrahiert: %s€", f"{budget:,}")

        # If we have local PDF files, run full analysis
        pdf_paths = getattr(project, "_pdf_local_paths", None)
        if not pdf_paths:
            return

        try:
            analyzer = TenderPdfAnalyzer()
            result = analyzer.analyze(pdf_paths)

            if result.extracted_text_length > 0:
                logger.info(
                    "  PDF-Analyse: %d Seiten, %d Zeichen",
                    result.total_pages,
                    result.extracted_text_length,
                )

                # Extract budget from PDF if not already set
                if not project.budget_max and result.budget_details:
                    for key in ["total_volume", "estimated_value", "max_value", "budget"]:
                        if key in result.budget_details:
                            budget = extract_budget_from_text(result.budget_details[key])
                            if budget:
                                project.budget_max = budget
                                logger.info("  Budget aus PDF: %s€", f"{budget:,}")
                                break

        except Exception as e:
            logger.warning("  PDF-Analyse fehlgeschlagen: %s", e)

    def _process_client(self, project: Project) -> tuple:
        """Process client information for a tender."""
        if project.client_name:
            client = get_or_create_client(self.db, project.client_name)
            increment_tender_seen(self.db, client)
            _, client_data = get_client_for_project(self.db, project)

            # Phase 2: Client Enrichment
            known_info = enrich_client(project.client_name)
            if known_info:
                client_data["known_client"] = True
                client_data["tech_affinity"] = known_info.tech_affinity
                client_data["preferred_stack"] = known_info.preferred_stack
                client_data["enrichment_score_modifier"] = get_client_score_modifier(project.client_name)
                logger.info("  Auftraggeber: %s (bekannt, Tech: %s)",
                            project.client_name[:40],
                            known_info.tech_affinity)
            else:
                client_data["known_client"] = False
                client_data["enrichment_score_modifier"] = 0
                logger.info("  Auftraggeber: %s (Win-Rate: %s)",
                            project.client_name[:40],
                            f"{client.win_rate:.0%}" if client.win_rate else "N/A")

            return client, client_data
        return None, {"win_rate": None, "tenders_applied": 0, "payment_rating": None, "known_client": False, "enrichment_score_modifier": 0}

    def _extract_lots(self, project: Project) -> List[TenderLot]:
        """Extract lots from a tender if applicable."""
        # Check description for lot indicators
        description = project.description or ""
        if not any(kw in description.lower() for kw in ["los 1", "los 2", "teil 1", "teil 2"]):
            return []

        logger.info("  Lose-Erkennung...")

        # Simple lot extraction (can be enhanced with pdf_analyzer)
        import re
        lot_pattern = r"(?:los|teil)\s*(\d+)[:\s]*([^\n]+)"
        matches = re.finditer(lot_pattern, description, re.IGNORECASE)

        lots = []
        for match in matches:
            lot_number = match.group(1)
            lot_title = match.group(2).strip()[:200]

            lot = TenderLot(
                project_id=project.id,
                lot_number=f"Los {lot_number}",
                lot_title=lot_title,
                status="new",
            )
            self.db.add(lot)
            lots.append(lot)
            self._stats.lots_extracted += 1

        if lots:
            self.db.commit()
            logger.info("  %d Lose extrahiert", len(lots))

        return lots

    def _process_lot(self, project: Project, lot: TenderLot, client_data: dict) -> None:
        """Process a single lot within a tender."""
        logger.info("    Los %s: %s...", lot.lot_number, (lot.lot_title or "")[:40])

        # Score the lot
        lot_description = lot.lot_description or project.description or ""
        score_result = score_tender(
            description=lot_description,
            pdf_text=project.pdf_text or "",
            budget_max=lot.lot_budget or project.budget_max,
            tender_deadline=project.tender_deadline,
            client_name=project.client_name,
            client_win_rate=client_data.get("win_rate"),
            client_tenders_applied=client_data.get("tenders_applied", 0),
            client_payment_rating=client_data.get("payment_rating"),
            title=lot.lot_title or project.title or "",
        )

        lot.score = score_result.normalized

        if score_result.skip:
            lot.status = "rejected"
            logger.info("      -> SKIP: %s", score_result.skip_reason)
        elif score_result.normalized >= settings.tender_score_threshold_review:
            lot.status = "review"
            logger.info("      -> REVIEW (Score: %d)", score_result.normalized)
        else:
            lot.status = "rejected"
            logger.info("      -> REJECT (Score: %d)", score_result.normalized)

        self.db.commit()

    def _score_and_decide(self, project: Project, client_data: dict) -> None:
        """Score a tender and make decision."""
        logger.info("  Scoring...")

        # Parse budget if available
        budget_max = project.budget_max or self._parse_budget(project.budget)

        # Detect procedure type
        procedure = detect_procedure_type(project.description or "")
        project.procedure_type = procedure
        logger.info("    Vergabeart: %s", procedure)

        # Check eligibility
        eligibility_status, eligibility_notes = check_eligibility(
            project.description or "",
            project.pdf_text or "",
        )
        project.eligibility_check = eligibility_status
        project.eligibility_notes = eligibility_notes
        logger.info("    Eignung: %s", eligibility_status)

        # Calculate score
        cpv_bonus = getattr(project, "_cpv_bonus", 0)
        score_result: TenderScore = score_tender(
            description=project.description or "",
            pdf_text=project.pdf_text or "",
            budget_max=budget_max,
            tender_deadline=project.tender_deadline,
            client_name=project.client_name,
            client_win_rate=client_data.get("win_rate"),
            client_tenders_applied=client_data.get("tenders_applied", 0),
            client_payment_rating=client_data.get("payment_rating"),
            cpv_bonus=cpv_bonus,
            title=project.title or "",
        )

        project.score = score_result.normalized
        logger.info("    Score: %d/100", score_result.normalized)
        for reason in score_result.reasons[:5]:
            logger.info("      - %s", reason)

        # Record decision
        self._record_decision(project, score_result)

        # Execute decision
        if score_result.skip:
            self._skip_tender(project, score_result.skip_reason)
        elif score_result.normalized >= settings.tender_score_threshold_review:
            self._add_to_review(project, score_result)
        else:
            self._reject_tender(project, score_result)

    def _parse_budget(self, budget_str: Optional[str]) -> Optional[int]:
        """Parse budget string to integer."""
        if not budget_str:
            return None

        import re
        # Try to find a number
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(mio|million|tsd|tausend|k|€|eur)?", budget_str.lower())
        if not match:
            return None

        value = float(match.group(1).replace(",", "."))
        unit = match.group(2) or ""

        if "mio" in unit or "million" in unit:
            return int(value * 1_000_000)
        elif "tsd" in unit or "tausend" in unit or unit == "k":
            return int(value * 1_000)
        else:
            return int(value)

    def _record_decision(self, project: Project, score_result: TenderScore) -> None:
        """Record decision for ML training."""
        # Determine recommendation
        if score_result.skip:
            recommendation = "reject"
        elif score_result.normalized >= settings.tender_score_threshold_review:
            recommendation = "review"
        else:
            recommendation = "reject"

        decision = TenderDecision(
            project_id=project.id,
            auto_score=score_result.normalized,
            auto_recommendation=recommendation,
            feature_vector={
                "tech_score": score_result.tech_score,
                "volume_score": score_result.volume_score,
                "procedure_score": score_result.procedure_score,
                "award_criteria_score": score_result.award_criteria_score,
                "eligibility_score": score_result.eligibility_score,
                "accessibility_score": score_result.accessibility_score,
                "security_score": score_result.security_score,
                "consortium_score": score_result.consortium_score,
                "client_score": score_result.client_score,
                "deadline_score": score_result.deadline_score,
            },
        )
        self.db.add(decision)

    def _skip_tender(self, project: Project, reason: str) -> None:
        """Skip a tender (blocker found)."""
        logger.info("  -> SKIP: %s", reason)

        rejection = RejectionReason(
            project_id=project.id,
            reason_code="TENDER_SKIP",
            explanation=reason,
        )
        self.db.add(rejection)
        project.status = PROJECT_STATUS_REJECTED
        self.db.commit()

        self._stats.skipped += 1

    def _add_to_review(self, project: Project, score_result: TenderScore) -> None:
        """Add tender to review queue."""
        priority = "high" if score_result.normalized >= settings.tender_score_threshold_review else "normal"
        logger.info("  -> REVIEW (%s, Score: %d)", priority, score_result.normalized)

        review = ReviewQueue(
            project_id=project.id,
            reason=f"Tender-Score {score_result.normalized}: {', '.join(score_result.reasons[:3])}",
        )
        self.db.add(review)
        project.status = PROJECT_STATUS_REVIEW
        self.db.commit()

        if score_result.normalized >= settings.tender_score_threshold_review:
            self._stats.high_priority += 1
            # Collect for email notification
            self._high_priority_tenders.append({
                "title": project.title,
                "score": score_result.normalized,
                "source": project.source,
                "url": project.url,
                "client_name": project.client_name or "-",
                "deadline": project.tender_deadline.strftime("%d.%m.%Y") if project.tender_deadline else "-",
            })
        self._stats.review_queue += 1

    def _reject_tender(self, project: Project, score_result: TenderScore) -> None:
        """Reject a tender."""
        logger.info("  -> REJECT (Score: %d)", score_result.normalized)

        rejection = RejectionReason(
            project_id=project.id,
            reason_code="TENDER_LOW_SCORE",
            explanation=f"Score {score_result.normalized} unter Schwellenwert {settings.tender_score_threshold_reject}",
        )
        self.db.add(rejection)
        project.status = PROJECT_STATUS_REJECTED
        self.db.commit()

        self._stats.rejected += 1


def run_tenders() -> TenderPipelineStats:
    """Execute the tender acquisition pipeline.

    Returns:
        TenderPipelineStats with run statistics
    """
    setup_logging(level=settings.log_level, log_file=settings.log_file)

    orchestrator = TenderOrchestrator()
    return orchestrator.run()


if __name__ == "__main__":
    run_tenders()
