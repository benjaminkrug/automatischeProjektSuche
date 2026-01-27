"""PDF Analyzer for tender documents.

Analyzes Vergabeunterlagen (procurement documents) to extract:
- Technical requirements
- Functional requirements
- Eligibility requirements
- Timeline information
- Budget details
- Award criteria
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class TechRequirement:
    """A technical requirement extracted from documents."""
    category: str  # e.g., "framework", "database", "infrastructure"
    requirement: str
    mandatory: bool = True
    source_page: Optional[int] = None


@dataclass
class EligibilityRequirement:
    """An eligibility requirement for tenderers."""
    category: str  # e.g., "revenue", "references", "certifications"
    description: str
    threshold: Optional[str] = None
    can_meet: Optional[bool] = None


@dataclass
class TimelineEntry:
    """A timeline entry from the tender."""
    event: str
    date: Optional[str] = None
    description: Optional[str] = None


@dataclass
class PdfAnalysisResult:
    """Complete result of PDF analysis."""
    tech_requirements: List[TechRequirement] = field(default_factory=list)
    functional_requirements: List[str] = field(default_factory=list)
    eligibility_requirements: List[EligibilityRequirement] = field(default_factory=list)
    timeline: List[TimelineEntry] = field(default_factory=list)
    budget_details: Dict[str, str] = field(default_factory=dict)
    award_criteria: Dict[str, int] = field(default_factory=dict)
    lot_info: List[Dict] = field(default_factory=list)
    total_pages: int = 0
    extracted_text_length: int = 0


class TenderPdfAnalyzer:
    """Analyzes tender procurement documents (PDFs)."""

    # Technical requirement patterns
    TECH_PATTERNS = {
        "framework": [
            r"(?:muss|soll|ist)?\s*(?:mit|in|unter)\s*(react|vue|angular|next\.?js|nuxt)",
            r"(react|vue|angular|flutter|kotlin|swift)\s*(?:anwendung|app|entwicklung)",
            r"technologie[:\s]+(.*?)(?=\n|$)",
        ],
        "database": [
            r"datenbank[:\s]+(postgresql|mysql|oracle|mongodb|mariadb)",
            r"(postgresql|mysql|oracle|mongodb)\s*(?:datenbank)?",
        ],
        "infrastructure": [
            r"(?:hosting|deployment|infrastruktur)[:\s]+(.*?)(?=\n|$)",
            r"(aws|azure|google\s*cloud|on-premise|kubernetes|docker)",
        ],
        "language": [
            r"programmiersprache[:\s]+(.*?)(?=\n|$)",
            r"(?:in|mit)\s*(python|java|typescript|c#|go)\s*(?:entwickelt|programmiert|umgesetzt)",
        ],
    }

    # Eligibility patterns
    ELIGIBILITY_PATTERNS = {
        "revenue": [
            r"mindestumsatz[:\s]+(\d+(?:[.,]\d+)?)\s*(mio|million|tsd|tausend|€|eur)?",
            r"jahresumsatz[:\s]+(?:mind(?:estens)?[:\s]+)?(\d+(?:[.,]\d+)?)\s*(mio|million|€)?",
        ],
        "references": [
            r"referenz(?:en|projekt)?[:\s]+(?:mind(?:estens)?[:\s]+)?(\d+)",
            r"(\d+)\s*vergleichbare\s*(?:projekt|referenz)",
            r"nachweis\s*(?:von|über)\s*(\d+)\s*(?:projekt|referenz)",
        ],
        "certifications": [
            r"(iso\s*\d+|bsi[- ]grundschutz|isms)",
            r"zertifizierung[:\s]+(.*?)(?=\n|$)",
        ],
        "insurance": [
            r"(betriebs?haftpflicht|berufshaftpflicht)[:\s]*(\d+(?:[.,]\d+)?)\s*(mio|million|€)?",
            r"versicherung[:\s]+(.*?)(?=\n|$)",
        ],
        "employees": [
            r"mindestens\s*(\d+)\s*mitarbeiter",
            r"(\d+)\s*(?:vollzeit)?mitarbeiter\s*(?:mindestens|minimum)",
        ],
    }

    # Award criteria patterns
    AWARD_PATTERNS = [
        r"preis[:\s]+(\d+)\s*%",
        r"qualität[:\s]+(\d+)\s*%",
        r"konzept[:\s]+(\d+)\s*%",
        r"referenz(?:en)?[:\s]+(\d+)\s*%",
        r"personal[:\s]+(\d+)\s*%",
        r"methodik[:\s]+(\d+)\s*%",
    ]

    # Lot extraction patterns
    LOT_PATTERNS = [
        r"los\s*(\d+|[a-z])[:\s]*(.*?)(?=los\s*\d|$)",
        r"teil(?:los)?\s*(\d+)[:\s]*(.*?)(?=teil(?:los)?\s*\d|$)",
    ]

    def __init__(self):
        """Initialize the analyzer."""
        self._pymupdf_available = self._check_pymupdf()

    def _check_pymupdf(self) -> bool:
        """Check if PyMuPDF is available."""
        try:
            import pymupdf  # noqa: F401
            return True
        except ImportError:
            try:
                import fitz  # noqa: F401
                return True
            except ImportError:
                logger.warning("PyMuPDF not installed. PDF analysis will be limited.")
                return False

    def analyze(self, pdf_paths: List[str]) -> PdfAnalysisResult:
        """Analyze one or more PDF documents.

        Args:
            pdf_paths: List of paths to PDF files

        Returns:
            PdfAnalysisResult with extracted information
        """
        result = PdfAnalysisResult()

        if not pdf_paths:
            return result

        combined_text = ""
        total_pages = 0

        for path in pdf_paths:
            try:
                text, pages = self._extract_text(path)
                combined_text += text + "\n\n"
                total_pages += pages
            except Exception as e:
                logger.error(f"Failed to extract text from {path}: {e}")

        result.total_pages = total_pages
        result.extracted_text_length = len(combined_text)

        if not combined_text:
            return result

        # Extract various requirements
        result.tech_requirements = self._extract_tech_requirements(combined_text)
        result.functional_requirements = self._extract_functional_requirements(combined_text)
        result.eligibility_requirements = self._extract_eligibility(combined_text)
        result.timeline = self._extract_timeline(combined_text)
        result.budget_details = self._extract_budget(combined_text)
        result.award_criteria = self._extract_award_criteria(combined_text)
        result.lot_info = self._extract_lots(combined_text)

        return result

    def _extract_text(self, pdf_path: str) -> tuple[str, int]:
        """Extract text from a PDF file.

        Returns:
            Tuple of (extracted_text, page_count)
        """
        if not self._pymupdf_available:
            return "", 0

        path = Path(pdf_path)
        if not path.exists():
            logger.warning(f"PDF file not found: {pdf_path}")
            return "", 0

        try:
            # Try pymupdf (newer name)
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz

            doc = fitz.open(pdf_path)
            text_parts = []

            for page_num, page in enumerate(doc):
                text = page.get_text()
                text_parts.append(f"--- Page {page_num + 1} ---\n{text}")

            doc.close()
            return "\n".join(text_parts), len(text_parts)

        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            return "", 0

    def _extract_tech_requirements(self, text: str) -> List[TechRequirement]:
        """Extract technical requirements from text."""
        requirements = []
        text_lower = text.lower()

        for category, patterns in self.TECH_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text_lower, re.IGNORECASE)
                for match in matches:
                    req_text = match.group(1) if match.lastindex else match.group(0)
                    req_text = req_text.strip()
                    if req_text and len(req_text) > 2:
                        # Check if mandatory
                        context_start = max(0, match.start() - 50)
                        context = text_lower[context_start:match.end()]
                        mandatory = "muss" in context or "zwingend" in context

                        requirements.append(TechRequirement(
                            category=category,
                            requirement=req_text,
                            mandatory=mandatory,
                        ))

        return requirements

    def _extract_functional_requirements(self, text: str) -> List[str]:
        """Extract functional requirements from text."""
        requirements = []

        # Look for numbered requirements
        numbered_pattern = r"(?:^|\n)\s*(?:\d+[\.\)]\s*)(.*?(?:muss|soll|ist\s+zu).*?)(?=\n\s*\d+[\.\)]|\n\n|$)"
        matches = re.finditer(numbered_pattern, text, re.IGNORECASE | re.MULTILINE)

        for match in matches:
            req = match.group(1).strip()
            if len(req) > 20 and len(req) < 500:
                requirements.append(req)

        return requirements[:20]  # Limit to top 20

    def _extract_eligibility(self, text: str) -> List[EligibilityRequirement]:
        """Extract eligibility requirements for tenderers."""
        requirements = []
        text_lower = text.lower()

        for category, patterns in self.ELIGIBILITY_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text_lower)
                for match in matches:
                    threshold = match.group(1) if match.lastindex else None

                    # Get context for description
                    context_start = max(0, match.start() - 20)
                    context_end = min(len(text_lower), match.end() + 100)
                    context = text[context_start:context_end].strip()

                    requirements.append(EligibilityRequirement(
                        category=category,
                        description=context[:200],
                        threshold=threshold,
                    ))

        return requirements

    def _extract_timeline(self, text: str) -> List[TimelineEntry]:
        """Extract timeline/deadline information."""
        timeline = []

        # Date patterns (German format)
        date_patterns = [
            r"(abgabefrist|einreichungsfrist|angebotsfrist)[:\s]+(\d{1,2}[\./]\d{1,2}[\./]\d{2,4})",
            r"(bindefrist|zuschlagsfrist)[:\s]+(\d{1,2}[\./]\d{1,2}[\./]\d{2,4})",
            r"(projektstart|leistungsbeginn)[:\s]+(\d{1,2}[\./]\d{1,2}[\./]\d{2,4})",
            r"(projektende|leistungsende)[:\s]+(\d{1,2}[\./]\d{1,2}[\./]\d{2,4})",
        ]

        for pattern in date_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                event = match.group(1)
                date = match.group(2)
                timeline.append(TimelineEntry(
                    event=event,
                    date=date,
                ))

        return timeline

    def _extract_budget(self, text: str) -> Dict[str, str]:
        """Extract budget information."""
        budget = {}

        patterns = [
            (r"geschätzter\s*(?:auftrags)?wert[:\s]+(\d+(?:[.,]\d+)?)\s*(mio|million|tsd|€)?", "estimated_value"),
            (r"höchstwert[:\s]+(\d+(?:[.,]\d+)?)\s*(mio|million|tsd|€)?", "max_value"),
            (r"gesamtvolumen[:\s]+(\d+(?:[.,]\d+)?)\s*(mio|million|tsd|€)?", "total_volume"),
            (r"budget[:\s]+(\d+(?:[.,]\d+)?)\s*(mio|million|tsd|€)?", "budget"),
        ]

        for pattern, key in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1)
                unit = match.group(2) if match.lastindex > 1 else ""
                budget[key] = f"{value} {unit}".strip()

        return budget

    def _extract_award_criteria(self, text: str) -> Dict[str, int]:
        """Extract award criteria weights."""
        criteria = {}

        for pattern in self.AWARD_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Extract criterion name from pattern
                criterion = pattern.split("[")[0].replace("\\", "").strip("()")
                weight = int(match.group(1))
                criteria[criterion] = weight

        return criteria

    def _extract_lots(self, text: str) -> List[Dict]:
        """Extract lot information from tender."""
        lots = []

        for pattern in self.LOT_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                lot_number = match.group(1)
                lot_description = match.group(2).strip()[:500] if match.lastindex > 1 else ""

                lots.append({
                    "lot_number": lot_number,
                    "description": lot_description,
                })

        return lots


def analyze_tender_pdfs(pdf_paths: List[str]) -> PdfAnalysisResult:
    """Convenience function to analyze tender PDFs.

    Args:
        pdf_paths: List of paths to PDF files

    Returns:
        PdfAnalysisResult with extracted information
    """
    analyzer = TenderPdfAnalyzer()
    return analyzer.analyze(pdf_paths)
