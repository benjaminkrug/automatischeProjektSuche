"""Orchestrator - Daily run coordinator.

Flow:
1. Scraping -> 2. Dedupe -> 3. Embeddings -> 4. Research -> 5. Matching -> 6. Decision -> 7. Documents -> 8. Logging
"""

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


def _run_async(coro):
    """Run async coroutine with proper event loop handling for Windows.

    This handles the case where we're running in a context (like Streamlit)
    that may already have an event loop.
    """
    # Setup Windows event loop policy for subprocess support
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Try to get existing event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're already in an async context, create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        # No running loop, use asyncio.run()
        return asyncio.run(coro)

from sqlalchemy.orm import Session

from app.ai.schemas import CandidateProfile, MatchResult, ResearchResult
from app.ai.embedding_search import find_top_matching_members
from app.ai.keyword_filter import check_project_keywords, KeywordCheckResult
from app.ai.keyword_scoring import calculate_keyword_score, KeywordScoreResult
from app.core.constants import (
    SEPARATOR_LINE,
    SEPARATOR_LINE_THIN,
    PROJECT_STATUS_APPLIED,
    PROJECT_STATUS_ERROR,
    PROJECT_STATUS_REJECTED,
    PROJECT_STATUS_REVIEW,
)
from app.core.container import ApplicationContainer, get_container
from app.core.exceptions import AkquiseBotError
from app.core.logging import setup_logging, get_logger
from app.db.models import (
    ApplicationLog,
    Project,
    RejectionReason,
    ReviewQueue,
    TeamMember,
)
from app.db.session import SessionLocal
from app.documents.generator import generate_application_folder
from app.services.ai_service import AIService
from app.services.client_research_service import get_client_research_sync, ClientResearch
from app.settings import settings
from app.sourcing.bund.scraper import BundScraper
from app.sourcing.bund_rss.scraper import BundRssScraper
from app.sourcing.evergabe.scraper import EvergabeScraper
from app.sourcing.evergabe_online.scraper import EvergabeOnlineScraper
from app.sourcing.freelancermap.scraper import FreelancermapScraper
from app.sourcing.gulp.scraper import GulpScraper
from app.sourcing.freelancede.scraper import FreelancedeScraper
from app.sourcing.ted.scraper import TedScraper
from app.sourcing.malt.scraper import MaltScraper
from app.sourcing.upwork.scraper import UpworkScraper
from app.sourcing.linkedin.scraper import LinkedinScraper
from app.sourcing.simap.scraper import SimapScraper
from app.sourcing.vergabe24.scraper import Vergabe24Scraper
from app.sourcing.normalize import save_projects, filter_old_projects, record_scraper_run
from app.sourcing.playwright.browser import browser_session

logger = get_logger("orchestrator")


@dataclass
class PipelineStats:
    """Statistics for a pipeline run."""

    scraped: int = 0
    new_projects: int = 0
    analyzed: int = 0
    applied: int = 0
    reviewed: int = 0
    rejected: int = 0
    errors: int = 0

    def log_summary(self) -> None:
        """Log summary statistics."""
        logger.info(SEPARATOR_LINE)
        logger.info("TAGESSTATISTIK")
        logger.info(SEPARATOR_LINE)
        logger.info("  Gescraped:        %d", self.scraped)
        logger.info("  Neue Projekte:    %d", self.new_projects)
        logger.info("  Analysiert:       %d", self.analyzed)
        logger.info("  Bewerbungen:      %d", self.applied)
        logger.info("  In Review:        %d", self.reviewed)
        logger.info("  Abgelehnt:        %d", self.rejected)
        logger.info("  Fehler:           %d", self.errors)
        logger.info(SEPARATOR_LINE)


class DailyOrchestrator:
    """Orchestrates the daily project acquisition pipeline."""

    def __init__(self, container: Optional[ApplicationContainer] = None):
        """Initialize orchestrator.

        Args:
            container: Optional DI container, uses global if not provided
        """
        self._container = container or get_container()
        self._db: Optional[Session] = None
        self._ai_service: Optional[AIService] = None
        self._stats = PipelineStats()

    @property
    def db(self) -> Session:
        """Get database session (lazy initialization)."""
        if self._db is None:
            self._db = self._container.get_db_session()
        return self._db

    @property
    def ai_service(self) -> AIService:
        """Get AI service (lazy initialization)."""
        if self._ai_service is None:
            self._ai_service = self._container.ai_service
        return self._ai_service

    def run(self) -> PipelineStats:
        """Execute the complete daily pipeline.

        Returns:
            PipelineStats with run statistics
        """
        logger.info(SEPARATOR_LINE)
        logger.info(
            "Akquise-Bot Daily Run - %s",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        logger.info(SEPARATOR_LINE)

        try:
            # 1. Scrape all portals
            raw_projects = _run_async(self._scrape_all_portals())

            # 2. Dedupe and save
            new_projects = self._save_and_dedupe(raw_projects)
            if not new_projects:
                logger.info("Keine neuen Projekte gefunden.")
                self._stats.log_summary()
                return self._stats

            # 3-7. Process each new project
            for project in new_projects:
                self._process_project(project)

            # 8. Log summary
            self._stats.log_summary()
            return self._stats

        except Exception as e:
            logger.error("Fehler in Pipeline: %s", e)
            self._stats.errors += 1
            raise

        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._db is not None:
            self._db.close()
            self._db = None

    async def _scrape_all_portals(self) -> List:
        """Scrape all configured portals."""
        logger.info("Phase 1: Scraping")
        logger.info(SEPARATOR_LINE_THIN)

        all_projects = []

        # Define all scrapers to run
        scrapers = [
            # Public sector - high priority
            ("bund.de", BundScraper()),
            ("bund_rss", BundRssScraper()),
            ("evergabe", EvergabeScraper()),
            ("evergabe_online", EvergabeOnlineScraper()),
            ("simap.ch", SimapScraper()),
            ("vergabe24", Vergabe24Scraper()),
            ("ted", TedScraper()),
            # Freelance portals
            ("freelancermap", FreelancermapScraper()),
            ("gulp", GulpScraper()),
            ("freelance.de", FreelancedeScraper()),
            ("malt", MaltScraper()),
            ("upwork", UpworkScraper()),
            ("linkedin", LinkedinScraper()),
        ]

        async with browser_session():
            for portal_name, scraper in scrapers:
                # Skip disabled portals
                if not scraper.is_enabled:
                    logger.info("[%s] Deaktiviert - übersprungen", portal_name)
                    continue

                logger.info("[%s]", portal_name)
                try:
                    projects = await scraper.scrape(max_pages=settings.scraper_max_pages)
                    scraped_count = len(projects)

                    # Filter old projects (published before last run)
                    projects, filtered_old = filter_old_projects(self.db, projects, portal_name)

                    all_projects.extend(projects)
                    self._stats.scraped += scraped_count

                    logger.info(
                        "  Gefunden: %d, nach Datumsfilter: %d Projekte",
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
                    # Continue with other scrapers even if one fails

        logger.info("Gesamt gescraped: %d Projekte", self._stats.scraped)
        return all_projects

    def _save_and_dedupe(self, raw_projects: List) -> List[Project]:
        """Save projects after deduplication."""
        logger.info("Phase 2: Deduplizierung")
        logger.info(SEPARATOR_LINE_THIN)

        saved = save_projects(self.db, raw_projects)
        self._stats.new_projects = len(saved)

        logger.info("Neue Projekte nach Dedupe: %d", len(saved))
        return saved

    def _process_project(self, project: Project) -> None:
        """Process a single project through the pipeline."""
        logger.info(SEPARATOR_LINE)
        logger.info("Projekt: %s...", project.title[:60])
        logger.info("Quelle: %s | ID: %s", project.source, project.external_id)
        logger.info(SEPARATOR_LINE)

        try:
            # Check capacity
            if not self._check_capacity(project):
                return

            # Phase 2.5: Detailed Keyword-Scoring (neues System)
            keyword_score_result = self._calculate_keyword_score_detailed(project)

            # Early reject based on keyword analysis
            if keyword_score_result.should_reject:
                self._reject_project(
                    project,
                    "KEYWORD_REJECT",
                    f"Ausschluss-Keywords gefunden: {', '.join(keyword_score_result.reject_keywords)}",
                )
                return

            # Skip LLM for very low keyword scores with high confidence (cost saving)
            if keyword_score_result.total_score < 10 and keyword_score_result.confidence == "high":
                logger.info(
                    "  Skip LLM - zu niedriger Keyword-Score: %d [%s]",
                    keyword_score_result.total_score,
                    keyword_score_result.confidence,
                )
                self._reject_project(
                    project,
                    "LOW_KEYWORD_SCORE",
                    f"Keyword-Score {keyword_score_result.total_score}/40 zu niedrig (Schwelle: 10)",
                )
                return

            # Phase 3: Find matching team members
            candidates = self._find_candidates(project)
            if not candidates:
                return

            # Phase 4: Research client
            research = self._research_project(project)

            # Phase 5: Match project (mit Keyword-Score)
            match_result = self._score_match(
                project, research, candidates, keyword_score_result
            )
            self._stats.analyzed += 1

            # Phase 6: Execute decision
            self._execute_decision(project, match_result, research)

            # Update project status
            project.analyzed_at = datetime.utcnow()
            project.proposed_rate = match_result.proposed_rate
            project.rate_reasoning = match_result.rate_reasoning
            self.db.commit()

        except Exception as e:
            logger.error("Fehler bei Verarbeitung: %s", e)
            self._stats.errors += 1
            project.status = PROJECT_STATUS_ERROR
            self.db.commit()

    def _check_capacity(self, project: Project) -> bool:
        """Check if we have capacity for new applications."""
        active_count = self._get_active_application_count()
        if active_count >= settings.max_active_applications:
            logger.info(
                "Kapazität erschöpft (%d/%d)",
                active_count,
                settings.max_active_applications,
            )
            self._add_to_review_queue(project, "Kapazitätsgrenze erreicht")
            return False
        return True

    def _check_keywords(self, project: Project) -> KeywordCheckResult:
        """Check project for boost and reject keywords (legacy).

        Note: This is kept for backwards compatibility. The new detailed
        keyword scoring is done via calculate_keyword_score_detailed().
        """
        logger.info("  Phase 2.5: Keyword-Filter (Legacy)...")
        result = check_project_keywords(
            project.title,
            project.description or "",
        )

        if result.boost:
            logger.info(
                "    Boost-Keywords: %s (+%d Punkte)",
                ", ".join(result.boost_keywords),
                result.score_modifier,
            )
        if result.reject:
            logger.info(
                "    Reject-Keywords: %s",
                ", ".join(result.reject_keywords),
            )

        return result

    def _calculate_keyword_score_detailed(self, project: Project) -> KeywordScoreResult:
        """Calculate detailed keyword score with tiers and combo bonuses.

        This is the new keyword scoring system that replaces the simple
        boost/reject logic with a detailed score breakdown.
        """
        logger.info("  Phase 2.5: Keyword-Scoring...")

        result = calculate_keyword_score(
            title=project.title,
            description=project.description or "",
            pdf_text=project.pdf_text or "",
        )

        # Log detailed breakdown
        if result.tier_1_keywords:
            logger.info(
                "    Tier-1 Keywords: %s (%d Punkte)",
                ", ".join(result.tier_1_keywords),
                result.tier_1_score,
            )
        if result.tier_2_keywords:
            logger.info(
                "    Tier-2 Keywords: %s (%d Punkte)",
                ", ".join(result.tier_2_keywords),
                result.tier_2_score,
            )
        if result.combo_bonus > 0:
            logger.info("    Combo-Bonus: +%d Punkte", result.combo_bonus)

        logger.info(
            "    Gesamt-Keyword-Score: %d/40 [%s]",
            result.total_score,
            result.confidence,
        )

        if result.should_reject:
            logger.info(
                "    REJECT-Keywords: %s (Score: %d)",
                ", ".join(result.reject_keywords),
                result.reject_score,
            )

        return result

    def _find_candidates(self, project: Project) -> List[CandidateProfile]:
        """Find matching team members for project."""
        logger.info("  Phase 3: Embedding-Suche...")
        description = project.description or project.title
        members_with_scores = find_top_matching_members(self.db, description, limit=3)

        if not members_with_scores:
            logger.info("  Keine passenden Kandidaten gefunden")
            self._reject_project(
                project,
                "TECH_STACK_MISMATCH",
                "Keine passenden Teammitglieder",
            )
            return []

        # Extract members and scores
        members = [m for m, _ in members_with_scores]
        scores = [s for _, s in members_with_scores]

        # Log scores for transparency
        for member, score in members_with_scores:
            logger.info("    %s: Embedding-Score %.3f", member.name, score)

        candidates = self.ai_service.create_candidate_profiles(members, embedding_scores=scores)
        logger.info("  Top-Kandidaten: %s", [c.name for c in candidates])
        return candidates

    def _research_project(self, project: Project) -> ResearchResult:
        """Research client and project."""
        logger.info("  Phase 4: Kundenrecherche...")

        # Fetch external research data if client name available
        external_data: ClientResearch | None = None
        if project.client_name:
            logger.info("    Deep-Recherche für: %s", project.client_name)
            try:
                external_data = get_client_research_sync(
                    self.db,
                    project.client_name,
                )
                if external_data and external_data.website:
                    logger.info("    Website gefunden: %s", external_data.website[:50])
                if external_data and external_data.kununu_rating:
                    logger.info("    Kununu-Bewertung: %.1f/5", external_data.kununu_rating)
            except Exception as e:
                logger.warning("    Deep-Recherche fehlgeschlagen: %s", e)

        research = self.ai_service.research_project(
            title=project.title,
            client_name=project.client_name,
            description=project.description,
            external_data=external_data,
        )
        logger.info("  Projekttyp: %s", research.project_type)
        logger.info("  Budget-Schätzung: %s", research.estimated_budget_range)
        return research

    def _score_match(
        self,
        project: Project,
        research: ResearchResult,
        candidates: List[CandidateProfile],
        keyword_result: KeywordScoreResult,
    ) -> MatchResult:
        """Score project-team match."""
        logger.info("  Phase 5: Matching...")
        if project.pdf_text:
            logger.info("    PDF-Text verfügbar (%d Zeichen)", len(project.pdf_text))
        active_count = self._get_active_application_count()

        match_result = self.ai_service.match_project_to_team(
            project_title=project.title,
            project_description=project.description or "",
            project_skills=project.skills,
            research=research,
            candidates=candidates,
            active_applications=active_count,
            public_sector=project.public_sector,
            keyword_score_modifier=0,  # Legacy, replaced by keyword_result
            pdf_text=project.pdf_text,
            keyword_result=keyword_result,
        )

        logger.info("  Score: %d/100", match_result.score)
        if match_result.score_breakdown:
            bd = match_result.score_breakdown
            logger.info(
                "    Aufschlüsselung: Skills=%d, Erfahrung=%d, Embedding=%d, Markt=%d, Risiko=%d",
                bd.skill_match, bd.experience, bd.embedding, bd.market_fit, bd.risk_factors
            )
        logger.info(
            "    (Keyword-Score: %d/40, Combo: +%d)",
            keyword_result.total_score,
            keyword_result.combo_bonus,
        )
        logger.info("  Entscheidung: %s", match_result.decision)
        logger.info("  Bester Kandidat: %s", match_result.best_candidate_name)
        return match_result

    def _execute_decision(
        self,
        project: Project,
        match_result: MatchResult,
        research: ResearchResult,
    ) -> None:
        """Execute the matching decision."""
        logger.info("  Phase 6: Entscheidung...")

        if match_result.decision == "apply":
            self._apply_to_project(project, match_result, research)
        elif match_result.decision == "review":
            self._add_to_review_queue(
                project,
                f"Score {match_result.score} - Review erforderlich",
            )
        else:
            self._reject_project(
                project,
                match_result.rejection_reason_code or "TECH_STACK_MISMATCH",
                f"Score {match_result.score} unter Schwellenwert",
            )

    def _get_active_application_count(self) -> int:
        """Get count of active (pending/in_progress) applications."""
        return (
            self.db.query(ApplicationLog)
            .filter(ApplicationLog.outcome.is_(None))
            .count()
        )

    def _apply_to_project(
        self,
        project: Project,
        match_result: MatchResult,
        research: ResearchResult,
    ) -> None:
        """Apply to a project - generate documents and log application."""
        logger.info("  -> Entscheidung: BEWERBEN")

        # Get team member
        member = (
            self.db.query(TeamMember)
            .filter(TeamMember.id == match_result.best_candidate_id)
            .first()
        )

        if not member:
            logger.error(
                "Teammitglied %d nicht gefunden",
                match_result.best_candidate_id,
            )
            return

        # Phase 7: Generate documents
        logger.info("  Phase 7: Dokumente generieren...")
        try:
            folder_path = generate_application_folder(
                project=project,
                member=member,
                match=match_result,
                research=research,
            )
            logger.info("  Ordner erstellt: %s", folder_path)

            # Log application
            app_log = ApplicationLog(
                project_id=project.id,
                team_member_id=member.id,
                match_score=match_result.score,
                proposed_rate=match_result.proposed_rate,
                public_sector=project.public_sector,
            )
            self.db.add(app_log)

            project.status = PROJECT_STATUS_APPLIED
            self.db.commit()

            self._stats.applied += 1
            logger.info("  Bewerbung erfolgreich vorbereitet!")

        except Exception as e:
            logger.error("Fehler bei Dokumentenerstellung: %s", e)
            self._stats.errors += 1

    def _add_to_review_queue(self, project: Project, reason: str) -> None:
        """Add project to review queue for manual decision."""
        logger.info("  -> Entscheidung: REVIEW (%s)", reason)

        review = ReviewQueue(
            project_id=project.id,
            reason=reason,
        )
        self.db.add(review)
        project.status = PROJECT_STATUS_REVIEW
        self.db.commit()

        self._stats.reviewed += 1

    def _reject_project(
        self,
        project: Project,
        reason_code: str,
        explanation: str,
    ) -> None:
        """Reject project with reason."""
        logger.info("  -> Entscheidung: ABLEHNEN (%s)", reason_code)

        rejection = RejectionReason(
            project_id=project.id,
            reason_code=reason_code,
            explanation=explanation,
        )
        self.db.add(rejection)
        project.status = PROJECT_STATUS_REJECTED
        self.db.commit()

        self._stats.rejected += 1


def run_daily() -> PipelineStats:
    """Execute the daily orchestration pipeline.

    Returns:
        PipelineStats with run statistics
    """
    # Setup logging
    setup_logging(level=settings.log_level, log_file=settings.log_file)

    orchestrator = DailyOrchestrator()
    return orchestrator.run()


if __name__ == "__main__":
    run_daily()
