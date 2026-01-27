from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, ARRAY
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
    # PDF analysis fields
    pdf_text = Column(Text)
    pdf_count = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_project_source_external_id"),
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
    """Tracks scraper runs for monitoring and analytics."""
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
