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

- **Parallelity limit**: Max 8 active applications at any time
- **Match thresholds**: <60 reject, 60-74 review, ≥75 apply
- **Pricing**: Always at lower market end, never below minimum hourly rate
- **Public sector**: Preferred (bonus in scoring)
- **Duplicates**: Prevented via (source, external_id) unique constraint
- **Cost target**: <2€/month for AI costs

## Database Tables

- `projects` - Scraped projects with status tracking
- `team_members` - Profiles with embeddings
- `application_logs` - Tracks outcomes for learning
- `rejection_reasons` - Standardized codes (BUDGET_TOO_LOW, TECH_STACK_MISMATCH, etc.)
- `review_queue` - Edge cases for manual review

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

## Orchestrator Flow

1. Scraping → 2. Dedupe → 3. Embeddings → 4. Research → 5. Matching → 6. Decision → 7. Documents → 8. Logging

---

## Current Implementation Status

### ✅ Completed (Foundation)
- `app/settings.py` - Konfiguration mit dotenv
- `app/db/session.py` - SQLAlchemy Engine + SessionLocal
- `app/db/models.py` - Alle 5 Tabellen (Project, TeamMember, RejectionReason, ReviewQueue, ApplicationLog)
- `app/orchestrator.py` - Placeholder für Pipeline
- `scripts/init_db.py` - DB-Initialisierung und Verifikation
- Verzeichnisstruktur: `app/sourcing/`, `app/ai/`, `app/documents/`, `templates/`, `output/`, `cvs/`

### 🔲 Next Steps
- Portal-Scraper implementieren (beginne mit bund.de)
- CrewAI Agents einrichten
- Embedding-Generierung für Team-Profile
- Matching-Logik
- Dokumenten-Generator

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

| Datei | Beschreibung |
|-------|--------------|
| `app/settings.py` | Lädt .env, Business-Konstanten (Thresholds, Embedding-Dimension) |
| `app/db/models.py` | SQLAlchemy Models für alle 5 Tabellen |
| `app/db/session.py` | Engine + SessionLocal Factory |
| `scripts/init_db.py` | Erstellt Tabellen, führt Test-Insert durch |
| `.env` | Credentials (nicht committen!) |
| `.env.example` | Template für .env |
