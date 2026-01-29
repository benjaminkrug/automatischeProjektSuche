"""Application settings using Pydantic Settings."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql://postgres:dev@localhost:5432/akquise",
        description="PostgreSQL connection URL",
    )
    db_pool_size: int = Field(default=5, ge=1, le=20, description="Connection pool size")
    db_pool_max_overflow: int = Field(
        default=10, ge=0, le=50, description="Max overflow connections"
    )

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI API key")

    # Embedding
    embedding_model: str = Field(
        default="text-embedding-3-small", description="OpenAI embedding model"
    )
    embedding_dimension: int = Field(
        default=1536, description="Embedding vector dimension"
    )

    # Business rules
    max_active_applications: int = Field(
        default=40, ge=1, le=50, description="Maximum concurrent applications"
    )
    match_threshold_reject: int = Field(
        default=60, ge=0, le=100, description="Score below which projects are rejected"
    )
    match_threshold_review: int = Field(
        default=74, ge=0, le=100, description="Score at or above which projects need review"
    )
    match_threshold_apply: int = Field(
        default=75, ge=0, le=100, description="Score at or above which to apply"
    )
    public_sector_bonus: int = Field(
        default=0, ge=0, le=20, description="Score bonus for public sector projects (deaktiviert)"
    )

    # Scraper settings
    scraper_timeout_ms: int = Field(
        default=30000, ge=5000, le=120000, description="Page load timeout in ms"
    )
    scraper_delay_seconds: float = Field(
        default=0.5, ge=0.1, le=5.0, description="Delay between requests in seconds"
    )
    scraper_max_pages: int = Field(
        default=1, ge=1, le=20, description="Maximum pages to scrape per portal"
    )

    # AI settings
    ai_model: str = Field(default="gpt-4o-mini", description="LLM model for analysis")
    ai_temperature: float = Field(
        default=0.3, ge=0.0, le=2.0, description="LLM temperature"
    )

    # Logging
    log_level: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    log_file: Optional[Path] = Field(
        default=None, description="Optional log file path"
    )

    # ============================================================
    # Tender Pipeline Settings (Ausschreibungen)
    # ============================================================
    max_active_tenders: int = Field(
        default=15, ge=1, le=20, description="Maximum concurrent tender applications"
    )
    tender_budget_min: int = Field(
        default=50000, ge=0, description="Minimum tender budget (EUR)"
    )
    tender_budget_max: int = Field(
        default=250000, ge=0, description="Maximum tender budget (EUR)"
    )
    tender_deadline_min_days: int = Field(
        default=14, ge=1, description="Minimum days until tender deadline"
    )
    tender_score_threshold_reject: int = Field(
        default=50, ge=0, le=100, description="Score below which tenders are rejected"
    )
    tender_score_threshold_review: int = Field(
        default=70, ge=0, le=100, description="Score at or above which tenders go to review"
    )

    # Email notifications
    notification_email: Optional[str] = Field(
        default=None, description="Email address for tender notifications"
    )
    smtp_host: Optional[str] = Field(default=None, description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: Optional[str] = Field(default=None, description="SMTP username")
    smtp_password: Optional[str] = Field(default=None, description="SMTP password")
    smtp_from: Optional[str] = Field(default=None, description="Sender email address")


# Singleton settings instance
settings = Settings()


# ============================================================
# Tender Tech Keywords
# ============================================================
TENDER_TECH_KEYWORDS = [
    "webanwendung", "webapp", "webapplikation",
    "mobile app", "ios", "android", "flutter",
    "react", "vue", "angular", "frontend",
    "portal", "plattform", "digitalisierung",
    "software-entwicklung", "softwareentwicklung",
    "app-entwicklung", "appentwicklung",
]

# Accessibility capabilities
ACCESSIBILITY_CAPABILITIES = {
    "wcag_2.1_aa": True,  # Können wir liefern
    "wcag_2.1_aaa": False,  # Zu aufwändig
    "bitv_2.0": True,
}

# Security capabilities
SECURITY_CAPABILITIES = {
    "bsi_grundschutz": False,  # Nicht zertifiziert
    "iso_27001": False,
    "dsgvo_konform": True,  # Können wir
    "penetrationstest": True,  # Können wir beauftragen
}

# Backwards compatibility exports
DATABASE_URL = settings.database_url
OPENAI_API_KEY = settings.openai_api_key
MAX_ACTIVE_APPLICATIONS = settings.max_active_applications
MATCH_THRESHOLD_REJECT = settings.match_threshold_reject
MATCH_THRESHOLD_REVIEW = settings.match_threshold_review
MATCH_THRESHOLD_APPLY = settings.match_threshold_apply
EMBEDDING_MODEL = settings.embedding_model
EMBEDDING_DIMENSION = settings.embedding_dimension
