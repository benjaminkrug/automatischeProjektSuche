🟢 Woche 1 – Fundament & Setup

Ziel: Projekt ist lauffähig, DB steht

To-Dos

Git-Repo anlegen

Projektstruktur erstellen

.env + .env.example

PostgreSQL lokal aufsetzen

Tabellen:

projects

team_members

rejection_reasons

review_queue

DB-Connection (SQLAlchemy)

Done wenn

Script kann DB lesen/schreiben

Dummy-Projekt speicherbar

🟢 Woche 2 – Teamprofile & CV-Handling

Ziel: Teamdaten sind strukturiert verfügbar

To-Dos

CV-Ordner definieren

CV-Pfad & Metadaten speichern

Teamprofil-Schema finalisieren

Text-Extraktion aus CVs

Embeddings für Teamprofile erzeugen

Done wenn

Alle Teammitglieder mit Embedding in DB

Profiltext reproduzierbar

🟢 Woche 3 – Playwright-Basis & 1. Portal (Bund.de)

Ziel: Reale Projekte kommen rein

To-Dos

Playwright Setup

Retry & Timeout

Bund.de Scraper:

Titel

Beschreibung

Auftraggeber

URL

External-ID (Hash)

Duplikatsprüfung

Done wenn

10+ echte Projekte in DB

Keine Duplikate

🟢 Woche 4 – Normalisierung & Orchestrator v1

Ziel: End-to-End ohne KI

To-Dos

Normalisiertes Projekt-Objekt

Orchestrator-Script:

Scrape → DB → Status new

Logging

Status-Handling

Done wenn

1 Script alle Projekte verarbeitet

Wiederholbar ohne Fehler

🟢 Woche 5 – CrewAI Setup & Researcher

Ziel: Auftraggeber-Recherche automatisiert

To-Dos

CrewAI installieren

Researcher-Agent bauen

DuckDuckGo Tool integrieren

Research-JSON definieren

Done wenn

Researcher liefert verwertbare Infos

JSON sauber & stabil

🟢 Woche 6 – Matcher v1 (ohne Feintuning)

Ziel: Erste KI-Entscheidungen

To-Dos

Matcher-Agent anlegen

Projekt + Teamprofile übergeben

Grobes Scoring

Apply / Reject Entscheidung

Done wenn

Matcher entscheidet konsistent

JSON-Output stabil

🟢 Woche 7 – Matcher FINAL (Produktionsprompt)

Ziel: Entscheidungsmaschine

To-Dos

Finalen System-Prompt integrieren

Scoring-Modell

Öffentlicher-Sektor-Bonus

Ablehnungs-Codes erzwingen

Done wenn

Jede Entscheidung erklärbar

Rejects fühlen sich „richtig“ an

🟢 Woche 8 – Angebotsstrategie (Low-End)

Ziel: Seriöse Preisvorschläge

To-Dos

Markt-Range-Ermittlung (KI)

Mindest-Stundensatz berücksichtigen

Angebot im Matcher-Output

DB-Felder erweitern

Done wenn

Jedes Apply hat einen Preis

Preise nachvollziehbar

🟢 Woche 9 – Parallelitäts-Logik (max. 8)

Ziel: Kein Overcommitment

To-Dos

Aktive Bewerbungen zählen

Apply blockieren bei >8

Ablehnungsgrund PARALLEL_LIMIT_REACHED

Done wenn

System sich selbst bremst

🟢 Woche 10 – Dokumentenerstellung

Ziel: Fertige Bewerbungsordner

To-Dos

Word-Template finalisieren

python-docx Integration

Ordnerstruktur

CV kopieren

Done wenn

Ordner ist sofort versendbar

🟢 Woche 11 – Review-Queue & Grenzfälle

Ziel: Manuelle Kontrolle minimieren

To-Dos

Review-Queue Tabelle nutzen

CLI-Script für Reviews

Status-Updates

Done wenn

Review nur selten nötig

🟢 Woche 12 – Feedback-Loop

Ziel: Lernendes System

To-Dos

Outcome-Tracking

Ablehnungsstatistik

Matcher-Prompt anreichern

Done wenn

System erkennbar besser filtert

🟢 Woche 13 – Weitere Portale (1–2)

Ziel: Mehr hochwertige Quellen

To-Dos

freelancermap

GULP oder TED

Wiederverwendung der Basis

Done wenn

Portale austauschbar

🟢 Woche 14 – Stabilisierung & Fehlerfälle

Ziel: Robustheit

To-Dos

Netzwerk-Fehler

LLM-Timeouts

Fallback-Entscheidungen

Done wenn

Daily Run stabil

🟢 Woche 15 – Logging & Kostenkontrolle

Ziel: Vertrauen ins System

To-Dos

Match-Score Logging

KI-Kosten pro Run

Laufzeit-Tracking

Done wenn

System erklärbar & auditierbar

🟢 Woche 16 – Refactoring & Abschluss

Ziel: Produktionsreife

To-Dos

Code aufräumen

README

Backup-Strategie

Erste echte Nutzung

Done wenn

Du vertraust dem System