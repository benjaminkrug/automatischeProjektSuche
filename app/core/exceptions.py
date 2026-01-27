"""Application exception hierarchy."""


class AkquiseBotError(Exception):
    """Base exception for all Akquise-Bot errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ScrapingError(AkquiseBotError):
    """Error during web scraping operations."""

    def __init__(
        self,
        message: str,
        source: str | None = None,
        url: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.source = source
        self.url = url


class AIProcessingError(AkquiseBotError):
    """Error during AI/LLM processing."""

    def __init__(
        self,
        message: str,
        model: str | None = None,
        prompt_preview: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.model = model
        self.prompt_preview = prompt_preview[:200] if prompt_preview else None


class ParsingError(AIProcessingError):
    """Error parsing AI output into structured format."""

    def __init__(
        self,
        message: str,
        raw_output: str | None = None,
        expected_schema: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details=details)
        self.raw_output = raw_output[:500] if raw_output else None
        self.expected_schema = expected_schema


class DatabaseError(AkquiseBotError):
    """Error during database operations."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        table: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.operation = operation
        self.table = table


class DocumentGenerationError(AkquiseBotError):
    """Error during document generation."""

    def __init__(
        self,
        message: str,
        template: str | None = None,
        output_path: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.template = template
        self.output_path = output_path
