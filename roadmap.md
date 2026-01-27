1. Projekt-Setup (Tag 1)
1.1 Repository & Struktur
akquise-bot/
│
├── app/
│   ├── orchestrator.py
│   ├── sourcing/
│   │   ├── base.py
│   │   ├── freelancemap.py
│   │   ├── bund.py
│   │   └── ted.py
│   ├── ai/
│   │   ├── crew.py
│   │   ├── researcher.py
│   │   └── matcher.py
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations.sql
│   ├── documents/
│   │   └── generator.py
│   └── utils/
│       └── scoring.py
│
├── templates/
│   └── anschreiben_template.docx
├── output/
├── scripts/
├── .env.example
├── requirements.txt
└── roadmap.md

1.2 Environment

Python 3.11+

PostgreSQL 15+

Abhängigkeiten:

playwright

crewai

openai

python-docx

psycopg2 / sqlalchemy

pgvector

python-dotenv

2. Datenbank & Datenmodell (Tag 1–2)
2.1 Tabellen anlegen

projects

team_members

review_queue

rejection_reasons

Pflichtfelder:

Projekt-Status (new, analyzed, matched, applied, rejected)

Angebotsdaten

Ablehnungsgrund

2.2 Duplikat-Schutz

Unique Constraint: (source, external_id)

Kein Projekt darf zweimal analysiert werden

3. Team-Profile & CV-Setup (Tag 2)
3.1 CV-Import

PDFs / DOCX manuell ablegen

Pfade in DB speichern

3.2 Strukturierte Profile

Rolle

Seniorität

Skills

Branchen

Sprachen

Mindest-Stundensatz

3.3 Embeddings (einmalig)

Profiltext → Embedding

Speicherung in team_members.profile_embedding

4. Sourcing / Scraping (Tag 3–4)
4.1 Playwright-Basis

Headless Browser

Retry & Timeout

Serverseitige Fehler tolerieren

4.2 Portale umsetzen (nacheinander)

Priorität:

Bund.de

TED

Freelancermap

GULP

Freelance.de

Malt

Upwork

LinkedIn Jobs

➡ Pro Portal:

eigener Scraper

normalisierte Ausgabe

4.3 Normalisierung

Jedes Projekt wird vereinheitlicht zu:

Titel

Beschreibung

Kunde

Quelle

URL

Öffentlicher Sektor: ja / nein

5. KI-Analyse (Tag 4–5)
5.1 CrewAI initialisieren

Agent 1: Researcher

Agent 2: Matcher

Modell: gpt-4o-mini

5.2 Researcher-Agent

Aufgaben:

Auftraggeber recherchieren

Webseite prüfen

Branche & Seriosität bewerten

Hinweise für Anschreiben liefern

5.3 Matcher-Agent (Kernstück)

Bewertet:

Fachliche Passung

Klarheit der Anforderungen

Auftraggeber-Risiko

Öffentlicher-Sektor-Bonus

Historische Erfolgsfaktoren

Parallelitäts-Limit (8)

Ergebnis:

apply / review / reject

Match-Score (0–100)

Angebotsvorschlag

Risiken

Ablehnungsgrund (falls zutreffend)

6. Angebotsstrategie (Tag 5)
6.1 Harte Regeln (Code)

Nie unter Mindest-Stundensatz

Immer unteres Marktende

Keine aggressiven Dumping-Preise

6.2 KI-Feinjustierung

KI liefert:

Stundensatz

sachliche Begründung

➡ Speicherung im Projekt

7. Entscheidungslogik (Tag 5)
7.1 Match-Thresholds

< 60 → Reject

60–74 → Review

≥ 75 → Apply

7.2 Parallelitäts-Kontrolle

Max. 8 aktive Bewerbungen

Wenn Limit erreicht:

keine neuen Ordner

Projekt wird verschoben oder abgelehnt

8. Dokumentenerstellung (Tag 6)
8.1 Ordnerstruktur
output/
  YYYY-MM-DD_Kunde_Projekt/

8.2 Anschreiben

Word-Template

Platzhalter:

Projektname

Kunde

Technische Argumente

Research-Insight

Stil:

sachlich

präzise

keine Werbesprache

8.3 CV-Handling

Genau ein CV

Automatisch kopieren

9. Ablehnungs-Intelligenz (Tag 6–7)
9.1 Pflicht bei jeder Ablehnung

Reason-Code

Erklärung

Geschätzte Erfolgswahrscheinlichkeit

9.2 Nutzung

Ablehnungsgründe fließen in Matcher-Bewertung ein

System lernt implizit

10. Orchestrierung & Betrieb (Tag 7)
10.1 Orchestrator

Reihenfolge:

Scraping

DB-Dedupe

Embeddings

Researcher

Matcher

Entscheidung

Dokumente

Status-Update

10.2 Cron

1× täglich (z. B. 06:00)

10.3 Logging

Scraping-Status

Match-Scores

Ablehnungsgründe

Fehler

Laufzeit

11. Definition of Done (DoD)

Kein Projekt doppelt verarbeitet

Jede Entscheidung erklärbar

Keine generischen Bewerbungen

Max. 8 parallele Bewerbungen

Öffentlicher Sektor bevorzugt

Kosten < 2 € / Monat

Erfolgsquote messbar