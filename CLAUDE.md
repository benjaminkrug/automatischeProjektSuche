# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated freelance project acquisition system ("Akquise-Bot") that:
- Scrapes freelance project portals daily
- Analyzes projects using AI (CrewAI with GPT-4o-mini)
- Matches projects against team profiles using embeddings
- Generates application documents for high-probability matches
- Learns from outcomes to improve future decisions

**Language**: German (all application documents, communication)
**Style**: Technical, factual - no marketing language

## Tech Stack

- Python 3.11+
- PostgreSQL 15+ with pgvector extension
- Playwright (headless Chromium)
- CrewAI for AI agents
- OpenAI SDK (text-embedding-3-small for embeddings)
- python-docx for document generation
- SQLAlchemy for database access

## Planned Architecture

```
app/
├── orchestrator.py      # Daily run coordinator
├── sourcing/            # Portal scrapers (one per portal)
│   ├── playwright/
│   └── normalize.py     # Unified project format
├── ai/
│   ├── crew.py          # CrewAI setup
│   ├── researcher.py    # Researches clients
│   ├── matcher.py       # Scores project-team fit
│   └── prompts/
├── db/
│   ├── models.py        # SQLAlchemy models
│   └── session.py
└── documents/
    ├── generator.py     # Creates application folders
    └── templates/
```

## Key Business Rules

### Freelance Pipeline
- **Parallelity limit**: Max 8 active applications at any time
- **Match thresholds**: <60 reject, 60-74 review, ≥75 apply
- **Pricing**: Always at lower market end, never below minimum hourly rate
- **Public sector**: Preferred (bonus in scoring)
- **Duplicates**: Prevented via (source, external_id) unique constraint
- **Cost target**: <2€/month for AI costs

### Tender Pipeline (Ausschreibungen)
- **Parallelity limit**: Max 3 active tender applications
- **Budget focus**: Gesamtvolumen 50k-250k EUR (not hourly rate)
- **Tech focus**: Web/Mobile App development only
- **Score thresholds**: <50 reject, 50-69 review, ≥70 high priority
- **Output**: Review queue only (no auto-apply)
- **Eligibility**: Checks for references, insurance, certifications

## Database Tables

### Core Tables
- `projects` - Scraped projects with status tracking (extended for tenders)
- `team_members` - Profiles with embeddings
- `application_logs` - Tracks outcomes for learning
- `rejection_reasons` - Standardized codes (BUDGET_TOO_LOW, TECH_STACK_MISMATCH, etc.)
- `review_queue` - Edge cases for manual review

### Tender-specific Tables
- `tender_config` - Tender pipeline configuration
- `tender_lots` - Individual lots within tenders
- `clients` - Vergabestellen history for learning
- `tender_decisions` - ML training data for manual decisions

## Portal Priority

**Public Sector (Aktiv):**
1. bund.de (Playwright)
2. bund_rss (RSS Feed - service.bund.de)
3. dtvp (Deutsches Vergabeportal)
4. evergabe.de (Aggregator)
5. evergabe-online.de (600+ Vergabestellen)
6. simap.ch (Schweiz)
7. TED (EU tenders)

**Freelance Portale (Aktiv):**
8. freelancermap
9. GULP
10. Freelance.de

**Deaktiviert:**
- Malt (kein öffentliches Projektlisting)
- LinkedIn Jobs (Login/Anti-Bot)
- Upwork (CAPTCHA/Anti-Bot)
- vergabe24 (liefert Infotexte statt Ausschreibungen)

## Pipeline Flows

### Freelance Pipeline (orchestrator.py)
1. Scraping → 2. Dedupe → 3. Embeddings → 4. Research → 5. Matching → 6. Decision → 7. Documents → 8. Logging

### Tender Pipeline (tender_orchestrator.py)
1. Scrape (public sector only) → 2. CPV Pre-Filter → 3. Dedupe → 4. Lot Extraction → 5. Budget Parsing → 6. PDF Analysis → 7. Tech Filter → 8. Procedure Scoring → 9. Eligibility Check → 10. Scoring → 11. Review Queue

---

## Current Implementation Status

### ✅ Completed (Foundation)
- `app/settings.py` - Konfiguration mit dotenv + Tender-Settings
- `app/db/session.py` - SQLAlchemy Engine + SessionLocal
- `app/db/models.py` - Alle Tabellen inkl. Tender-Tabellen
- `app/orchestrator.py` - Freelance Pipeline
- `app/tender_orchestrator.py` - Tender Pipeline
- `scripts/init_db.py` - DB-Initialisierung und Verifikation
- Verzeichnisstruktur: `app/sourcing/`, `app/ai/`, `app/documents/`, `templates/`, `output/`, `cvs/`

### ✅ Tender Pipeline (Separate Ausschreibungs-Pipeline)
- `app/tender_orchestrator.py` - Separate Pipeline für öffentliche Ausschreibungen
- `app/sourcing/cpv_filter.py` - CPV-Code Pre-Filter
- `app/sourcing/tender_filter.py` - Scoring + Eignungsprüfung
- `app/sourcing/pdf_analyzer.py` - PDF-Analyse für Vergabeunterlagen
- `app/sourcing/client_db.py` - Auftraggeber-Verwaltung
- `scripts/run_tenders.py` - Entry Point
- `tests/test_tender_pipeline.py` - Unit Tests

### ✅ UI-Integration Tender-Pipeline
- `app/ui/app.py` - Dashboard mit Tender-Kapazität + Pipeline-Buttons
- `app/ui/queries.py` - Tender-spezifische Abfragen (20+ Funktionen)
- `app/ui/pages/1_Projekte.py` - Projekt-Typ Filter + Tender-Spalten
- `app/ui/pages/3_Review.py` - Score-Breakdown, Deadline-Ampel, Quick-Actions
- `app/ui/pages/6_Ausschreibungen.py` - Separate Tender-Ansicht mit Lose, Export
- `app/ui/pages/7_Auftraggeber.py` - Vergabestellen-DB mit Bewertungen

### 🔲 Next Steps
- CrewAI Agents einrichten
- Embedding-Generierung für Team-Profile
- Dokumenten-Generator für Freelance-Pipeline
- ML-Feedback-Loop für Tender-Pipeline (Phase 2)

---

## Development Setup

### Voraussetzungen
- Python 3.11+ (installiert via winget)
- Docker Desktop
- OpenAI API-Key

### Environment starten

```bash
# 1. Virtual Environment aktivieren
# Windows CMD:
venv\Scripts\activate
# Git Bash:
source venv/Scripts/activate

# 2. PostgreSQL Container starten (falls nicht läuft)
docker start akquise-db
# Oder neu erstellen:
docker run -d --name akquise-db -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=akquise -p 5432:5432 pgvector/pgvector:pg16

# 3. pgvector Extension aktivieren (einmalig)
docker exec akquise-db psql -U postgres -d akquise -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 4. Tabellen erstellen (einmalig)
python scripts/init_db.py
```

### Konfiguration
Datei `.env` im Projektroot:
```
DATABASE_URL=postgresql://postgres:dev@localhost:5432/akquise
OPENAI_API_KEY=sk-...
```

### Nützliche Befehle

```bash
# DB-Tabellen anzeigen
docker exec akquise-db psql -U postgres -d akquise -c "\dt"

# Projekte abfragen
docker exec akquise-db psql -U postgres -d akquise -c "SELECT id, source, title, status FROM projects;"

# Container-Status prüfen
docker ps -a --filter "name=akquise-db"

# Dependencies installieren
pip install -r requirements.txt

# Playwright Browser installieren
playwright install chromium
```

---

## File Reference

### Core
| Datei | Beschreibung |
|-------|--------------|
| `app/settings.py` | Lädt .env, Business-Konstanten, Tender-Settings |
| `app/db/models.py` | SQLAlchemy Models (Core + Tender) |
| `app/db/session.py` | Engine + SessionLocal Factory |
| `scripts/init_db.py` | Erstellt Tabellen, führt Test-Insert durch |
| `.env` | Credentials (nicht committen!) |
| `.env.example` | Template für .env |

### Freelance Pipeline
| Datei | Beschreibung |
|-------|--------------|
| `app/orchestrator.py` | Freelance Pipeline Koordinator |
| `scripts/run_freelance.py` | Entry Point |

### Tender Pipeline
| Datei | Beschreibung |
|-------|--------------|
| `app/tender_orchestrator.py` | Tender Pipeline Koordinator |
| `app/sourcing/cpv_filter.py` | CPV-Code Pre-Filter für EU-Ausschreibungen |
| `app/sourcing/tender_filter.py` | Scoring, Tech-Analyse, Eignungsprüfung |
| `app/sourcing/pdf_analyzer.py` | PDF-Extraktion für Vergabeunterlagen |
| `app/sourcing/client_db.py` | Auftraggeber-Historie für Lerneffekte |
| `scripts/run_tenders.py` | Entry Point |

### Tests
| Datei | Beschreibung |
|-------|--------------|
| `tests/test_tender_pipeline.py` | Unit Tests für Tender-Pipeline |

### UI
| Datei | Beschreibung |
|-------|--------------|
| `app/ui/app.py` | Dashboard mit Freelance + Tender Kapazität |
| `app/ui/queries.py` | Alle DB-Abfragen inkl. Tender-spezifisch |
| `app/ui/pages/1_Projekte.py` | Projektliste mit Typ-Filter |
| `app/ui/pages/2_Team.py` | Teammitglieder-Verwaltung |
| `app/ui/pages/3_Review.py` | Review Queue (Freelance + Tender) |
| `app/ui/pages/4_Bewerbungen.py` | Bewerbungslog |
| `app/ui/pages/5_Analytics.py` | Analytics Dashboard |
| `app/ui/pages/6_Ausschreibungen.py` | Tender-spezifische Ansicht |
| `app/ui/pages/7_Auftraggeber.py` | Vergabestellen-Datenbank |

---

## Running the Pipelines

```bash
# Freelance Pipeline (existing)
python -m app.orchestrator

# Tender Pipeline (new)
python scripts/run_tenders.py

# Or via module
python -m app.tender_orchestrator
```

## Tender Scoring System

| Kriterium | Max. Punkte | Beschreibung |
|-----------|-------------|--------------|
| Tech-Fit: Web | 20 | Webanwendung explizit gefordert |
| Tech-Fit: Mobile | 20 | Mobile App explizit gefordert |
| Tech-Stack Bonus | 10 | Bekannte Technologien (React, Flutter, etc.) |
| Volumen | 15 | Bonus für Zielkorridor 50k-250k EUR |
| Vergabeart | 15 | Verhandlungsverfahren bevorzugt |
| Zuschlagskriterien | 10 | Qualität > Preis bevorzugt |
| Eignung | 15 | Anforderungen erfüllbar |
| Barrierefreiheit | 5 | BITV/WCAG erfüllbar |
| Sicherheit | 0/-20 | Blocker (BSI/ISO) |
| Bietergemeinschaft | 10 | KMU-freundlich |
| Auftraggeber | 15 | Bekannter Kunde + gute Win-Rate |
| Deadline | 10 | ≥21 Tage bis Abgabe |

**Blocker (sofortige Ablehnung):**
- Kein Tech-Fit (weder Web noch Mobile)
- Sicherheitsanforderung nicht erfüllbar (z.B. ISO 27001)
- Bietergemeinschaft nötig aber nicht erlaubt
