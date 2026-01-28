from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, ARRAY, JSON, Index
)
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

from app.settings import EMBEDDING_DIMENSION

Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    url = Column(Text)
    title = Column(String(500), nullable=False)
    client_name = Column(String(255))
    description = Column(Text)
    skills = Column(ARRAY(String))
    budget = Column(String(100))
    location = Column(String(255))
    remote = Column(Boolean, default=False)
    public_sector = Column(Boolean, default=False)
    proposed_rate = Column(Float)
    rate_reasoning = Column(Text)
    status = Column(String(50), default="new")
    scraped_at = Column(DateTime, default=datetime.utcnow)
    analyzed_at = Column(DateTime)
    # Publication date (when the project was published on the portal)
    published_at = Column(DateTime)
    # PDF analysis fields
    pdf_text = Column(Text)
    pdf_count = Column(Integer, default=0)

    # Tender-specific fields
    project_type = Column(String(20), default="freelance")  # "freelance" | "tender"
    budget_min = Column(Integer)  # Parsed Budget (EUR)
    budget_max = Column(Integer)  # Parsed Budget (EUR)
    tender_deadline = Column(DateTime)  # Abgabefrist
    cpv_codes = Column(ARRAY(String))  # EU-Klassifikation
    eligibility_check = Column(String(20))  # "pass" | "fail" | "unclear"
    eligibility_notes = Column(Text)  # Details zu Anforderungen
    procedure_type = Column(String(50))  # Vergabeart
    score = Column(Integer)  # Berechneter Score

    # Keyword-Scoring (persistiert für Audit-Trail) - M2
    keyword_score = Column(Integer, nullable=True)  # 0-40 Gesamt
    keyword_confidence = Column(String(10), nullable=True)  # high/medium/low
    keyword_tier_1 = Column(ARRAY(String), nullable=True)  # Gefundene T1-Keywords
    keyword_tier_2 = Column(ARRAY(String), nullable=True)  # Gefundene T2-Keywords
    keyword_reject = Column(ARRAY(String), nullable=True)  # Gefundene Reject-Keywords
    keyword_combo_bonus = Column(Integer, nullable=True)  # Combo-Bonus

    # Processing state for resume/checkpoint - M4
    processing_state = Column(String(20), default="pending")  # pending/embedding/research/matching/done/error

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_project_source_external_id"),
        # Q3: Status-Filter für Orchestrator
        Index("ix_projects_status", "status"),
        Index("ix_projects_project_type", "project_type"),
        Index("ix_projects_analyzed_at", "analyzed_at"),
        # Tender-spezifisch
        Index("ix_projects_eligibility_check", "eligibility_check"),
        Index("ix_projects_score", "score"),
        # Composite für häufige Patterns
        Index("ix_projects_type_status", "project_type", "status"),
        # Processing state for resume
        Index("ix_projects_processing_state", "processing_state"),
    )

    rejection_reasons = relationship("RejectionReason", back_populates="project")
    review_queue_entries = relationship("ReviewQueue", back_populates="project")
    application_logs = relationship("ApplicationLog", back_populates="project")


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    role = Column(String(100))
    seniority = Column(String(50))
    skills = Column(ARRAY(String))
    industries = Column(ARRAY(String))
    languages = Column(ARRAY(String))
    years_experience = Column(Integer)
    min_hourly_rate = Column(Float)
    cv_path = Column(String(500))
    profile_text = Column(Text)
    profile_embedding = Column(Vector(EMBEDDING_DIMENSION))
    active = Column(Boolean, default=True)

    application_logs = relationship("ApplicationLog", back_populates="team_member")


class RejectionReason(Base):
    __tablename__ = "rejection_reasons"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    reason_code = Column(String(50), nullable=False)
    explanation = Column(Text)
    estimated_success_probability = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="rejection_reasons")


class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    resolution = Column(String(50))

    __table_args__ = (
        # Q3: Indizes für Review-Queue
        Index("ix_review_queue_project_id", "project_id"),
        Index("ix_review_queue_resolved_at", "resolved_at"),
    )

    project = relationship("Project", back_populates="review_queue_entries")


class ApplicationLog(Base):
    __tablename__ = "application_logs"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    team_member_id = Column(Integer, ForeignKey("team_members.id"), nullable=False)
    match_score = Column(Float)
    proposed_rate = Column(Float)
    public_sector = Column(Boolean, default=False)
    applied_at = Column(DateTime, default=datetime.utcnow)
    outcome = Column(String(50))
    outcome_at = Column(DateTime)

    __table_args__ = (
        # Q3: Indizes für Application-Logs
        Index("ix_application_logs_project_id", "project_id"),
        Index("ix_application_logs_outcome", "outcome"),
        Index("ix_application_logs_team_member_id", "team_member_id"),
    )

    project = relationship("Project", back_populates="application_logs")
    team_member = relationship("TeamMember", back_populates="application_logs")


class ClientResearchCache(Base):
    """Cache for client/company research data."""
    __tablename__ = "client_research_cache"

    id = Column(Integer, primary_key=True)
    client_name_normalized = Column(String(255), unique=True, nullable=False)
    company_website = Column(Text)
    company_about_text = Column(Text)
    hrb_number = Column(String(50))
    founding_year = Column(Integer)
    employee_count = Column(String(50))
    kununu_rating = Column(Float)
    last_updated = Column(DateTime, default=datetime.utcnow)


class ScraperRun(Base):
    """Tracks scraper runs for monitoring and analytics (M6: Health Monitoring)."""
    __tablename__ = "scraper_runs"

    id = Column(Integer, primary_key=True)
    portal = Column(String(50), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    status = Column(String(20), default="running")  # running, success, error
    projects_found = Column(Integer, default=0)
    new_projects = Column(Integer, default=0)
    duplicates = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    error_details = Column(Text)  # JSON array of error details
    duration_seconds = Column(Float)

    # M6: Indizes für Scraper Health Monitoring
    __table_args__ = (
        Index("ix_scraper_runs_portal_started", "portal", "started_at"),
        Index("ix_scraper_runs_status", "status"),
    )


class AIUsage(Base):
    """Tracks AI API usage for cost monitoring."""
    __tablename__ = "ai_usage"

    id = Column(Integer, primary_key=True)
    operation = Column(String(50), nullable=False)  # embedding, research, matching
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    model = Column(String(50), default="gpt-4o-mini")
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)


# ============================================================
# Tender Pipeline Models (Ausschreibungen)
# ============================================================


class TenderConfig(Base):
    """Configuration for tender pipeline."""
    __tablename__ = "tender_config"

    id = Column(Integer, primary_key=True)
    max_active_tenders = Column(Integer, default=3)
    budget_min = Column(Integer, default=50000)
    budget_max = Column(Integer, default=250000)
    required_tech_keywords = Column(ARRAY(String))
    excluded_keywords = Column(ARRAY(String))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TenderLot(Base):
    """Individual lots within a tender (Lose)."""
    __tablename__ = "tender_lots"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    lot_number = Column(String(50))  # "Los 1", "Lot A", etc.
    lot_title = Column(String(500))
    lot_description = Column(Text)
    lot_budget = Column(Integer)
    lot_cpv_codes = Column(ARRAY(String))
    score = Column(Integer)
    status = Column(String(20), default="new")  # "new", "review", "rejected"
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", backref="tender_lots")


class Client(Base):
    """Vergabestellen-Historie für Lerneffekte."""
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False)  # Normalisierter Name
    aliases = Column(ARRAY(String))  # Alternative Schreibweisen
    sector = Column(String(50))  # "bund", "land", "kommune", "eu"

    # Historie
    tenders_seen = Column(Integer, default=0)  # Anzahl Ausschreibungen
    tenders_applied = Column(Integer, default=0)
    tenders_won = Column(Integer, default=0)
    win_rate = Column(Float)

    # Bewertung
    payment_rating = Column(Integer)  # 1-5 Sterne
    communication_rating = Column(Integer)
    notes = Column(Text)

    # Kontakte
    known_contacts = Column(JSON)  # [{"name": "...", "email": "..."}]

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TenderDecision(Base):
    """Speichert manuelle Entscheidungen für späteres ML-Training."""
    __tablename__ = "tender_decisions"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    lot_id = Column(Integer, ForeignKey("tender_lots.id"))

    # System-Score
    auto_score = Column(Integer)
    auto_recommendation = Column(String(20))  # "apply", "review", "reject"

    # Manuelle Entscheidung
    manual_decision = Column(String(20))  # "apply", "skip", "partner_needed"
    decision_reason = Column(Text)  # Freitext
    decision_by = Column(String(100))  # User
    decision_at = Column(DateTime)

    # Features für ML (später)
    feature_vector = Column(JSON)  # Serialisierte Features

    # Outcome (wenn bekannt)
    outcome = Column(String(20))  # "won", "lost", "withdrew"
    outcome_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", backref="tender_decisions")
    lot = relationship("TenderLot", backref="tender_decisions")


# ============================================================
# Phase 2/3 Models
# ============================================================

# Note: ScraperStats removed - use ScraperRun instead (already exists with same functionality)


class ScoreHistory(Base):
    """A3: Historie aller Score-Berechnungen für ML-Training."""
    __tablename__ = "score_history"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    # Gesamt-Scores
    total_score = Column(Integer, nullable=False)
    keyword_score = Column(Integer)
    embedding_score = Column(Float)

    # Breakdown
    tier_1_score = Column(Integer)
    tier_2_score = Column(Integer)
    tier_3_score = Column(Integer)
    combo_bonus = Column(Integer)

    # Kontext
    model_version = Column(String(50))  # z.B. "v1.2.0"
    confidence = Column(String(10))

    # Decision
    decision = Column(String(20))  # apply/review/reject
    decision_reason = Column(Text)

    __table_args__ = (
        Index("ix_score_history_project_id", "project_id"),
        Index("ix_score_history_calculated_at", "calculated_at"),
    )

    project = relationship("Project", backref="score_history")
