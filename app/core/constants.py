"""Application constants."""

# Display formatting
SEPARATOR_LINE = "=" * 60
SEPARATOR_LINE_THIN = "-" * 40

# Rejection reason codes (mit Beschreibungen)
REJECTION_CODES = [
    # Bestehend
    "BUDGET_TOO_LOW",
    "TECH_STACK_MISMATCH",
    "EXPERIENCE_INSUFFICIENT",
    "TIMELINE_CONFLICT",
    "CAPACITY_FULL",
    "KEYWORD_MISMATCH",
    # NEU: Team-Passung
    "TEAM_SIZE_MISMATCH",  # Projekt erfordert mehr als 3 Personen
    "PROJECT_TOO_LARGE",  # Projektumfang zu groß für Team
    "BUDGET_TOO_HIGH",  # Budget über €250.000 Limit
    # NEU: Projekttyp
    "NOT_WEBAPP",  # Kein Webapp/App-Projekt
    # NEU: Bietergemeinschaft-Barrieren
    "REFERENCES_REQUIRED",  # Referenzen erforderlich, die wir nicht haben
    "CERTIFICATION_REQUIRED",  # Zertifizierung erforderlich (ISO, BSI, etc.)
    "SECURITY_CLEARANCE",  # Sicherheitsüberprüfung erforderlich
    "LEGAL_FORM_MISMATCH",  # Rechtsform passt nicht (GmbH verlangt)
    "BG_NOT_ALLOWED",  # Bietergemeinschaft ausgeschlossen
    "MIN_SIZE_NOT_MET",  # Mindestumsatz/Mitarbeiterzahl nicht erfüllt
]

# Rejection reason descriptions (für UI-Anzeige)
REJECTION_DESCRIPTIONS = {
    "BUDGET_TOO_LOW": "Budget unter Mindestrate",
    "TECH_STACK_MISMATCH": "Technologie passt nicht",
    "EXPERIENCE_INSUFFICIENT": "Erfahrung nicht ausreichend",
    "TIMELINE_CONFLICT": "Zeitrahmen nicht machbar",
    "CAPACITY_FULL": "Keine Kapazität verfügbar",
    "KEYWORD_MISMATCH": "Ausschluss-Keywords gefunden",
    # Team-Passung
    "TEAM_SIZE_MISMATCH": "Projekt erfordert mehr als 3 Personen",
    "PROJECT_TOO_LARGE": "Projektumfang zu groß für Team",
    "BUDGET_TOO_HIGH": "Budget über €250.000 Limit",
    # Projekttyp
    "NOT_WEBAPP": "Kein Webapp/App-Projekt",
    # Bietergemeinschaft-Barrieren
    "REFERENCES_REQUIRED": "Referenzen erforderlich, die wir nicht haben",
    "CERTIFICATION_REQUIRED": "Zertifizierung erforderlich (ISO, BSI, etc.)",
    "SECURITY_CLEARANCE": "Sicherheitsüberprüfung erforderlich",
    "LEGAL_FORM_MISMATCH": "Rechtsform passt nicht (GmbH verlangt)",
    "BG_NOT_ALLOWED": "Bietergemeinschaft ausgeschlossen",
    "MIN_SIZE_NOT_MET": "Mindestumsatz/Mitarbeiterzahl nicht erfüllt",
}

# Project status values
PROJECT_STATUS_NEW = "new"
PROJECT_STATUS_ANALYZED = "analyzed"
PROJECT_STATUS_APPLIED = "applied"
PROJECT_STATUS_REVIEW = "review"
PROJECT_STATUS_REJECTED = "rejected"
PROJECT_STATUS_ERROR = "error"

# Decision types
DECISION_APPLY = "apply"
DECISION_REVIEW = "review"
DECISION_REJECT = "reject"
