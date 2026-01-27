0. Projektdefinition & Leitplanken
0.1 Ziel des Systems

Ein täglich laufendes, vollautomatisches System, das:

relevante Freelance-Projekte findet

diese inhaltlich und strategisch analysiert

Auftraggeber recherchiert

Projekte mit internen Teamprofilen matched

nur bei hoher Erfolgswahrscheinlichkeit Bewerbungsunterlagen erzeugt

Entscheidungen dokumentiert (inkl. Ablehnungen)

aus Ergebnissen lernt

langfristig die Erfolgsquote steigert

0.2 Explizite Nicht-Ziele

Das System soll nicht:

möglichst viele Bewerbungen versenden

aggressiv verkaufen

generische Anschreiben erzeugen

Preise maximieren

Blacklists manuell pflegen

0.3 Feste Rahmenbedingungen (entscheidend)
Bereich	Festlegung
Teamgröße	max. 5 Personen
Bewerbung	1 Bewerbung = 1 Profil
Sprache	Deutsch
Stil	technisch, nüchtern
Ziel	maximale Erfolgsquote
Angebotsstrategie	KI-gestützt, unteres Marktende
Öffentlicher Sektor	bevorzugen
Parallelität	max. 8 aktive Bewerbungen
Blacklist	nein
Laufzeit	1x täglich
KI-Kosten	< 2 € / Monat
1. Projekt-Setup & Infrastruktur
1.1 Repository-Struktur
automated-freelance-acquisition/
├── app/
│   ├── sourcing/
│   │   ├── playwright/
│   │   ├── normalize.py
│   │   └── __init__.py
│   ├── ai/
│   │   ├── crew.py
│   │   ├── researcher.py
│   │   ├── matcher.py
│   │   ├── pricing.py
│   │   └── prompts/
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   ├── documents/
│   │   ├── generator.py
│   │   └── templates/
│   ├── analytics/
│   │   ├── analyze_results.py
│   │   └── reports/
│   ├── orchestrator.py
│   └── settings.py
├── scripts/
├── output/
├── .env.example
├── requirements.txt
├── README.md
└── roadmap.md

1.2 Technische Basis

Python ≥ 3.11

PostgreSQL ≥ 15

pgvector Extension

Playwright (Chromium)

CrewAI

OpenAI SDK

DuckDuckGo Search API

1.3 Sicherheits-Grundsätze

Keine API-Keys im Code

.env niemals committen

Logging ohne sensible Inhalte

KI-Prompts versionieren

2. Datenbank – Fundament des Systems
2.1 Grundprinzipien

Alles entscheidungsrelevante wird gespeichert

Keine impliziten Entscheidungen

Jede Ablehnung ist erklärbar

Historie ist wichtiger als aktuelle Meinung

2.2 Tabellen – Übersicht

projects

team_members

application_logs

rejection_reasons

review_queue

2.3 Tabelle: projects

Zweck:
Zentrale Projekt-Entität, unabhängig von Bewerbungen.

Wichtige Prinzipien:

Ein Projekt kann analysiert, aber nie beworben worden sein

Duplikate sind ausgeschlossen

Status ist explizit

Felder (Auszug, vollständig):

source

external_id

url

title

client_name

description

skills

budget

location

remote

public_sector (boolean)

proposed_rate

rate_reasoning

status

scraped_at

analyzed_at

2.4 Tabelle: team_members

Zweck:
Strukturierte Repräsentation realer Personen.

Prinzipien:

CVs werden nicht ständig neu gelesen

Profile sind stabil

Embeddings nur bei Änderung

Felder:

name

role

seniority

skills

industries

languages

years_experience

cv_path

profile_embedding

active

2.5 Tabelle: application_logs

Zweck:
Messung von Erfolg – nicht projects!

Prinzip:

Bewerbung = eigener Datensatz

Grundlage aller KPIs

Felder:

project_id

team_member_id

match_score

proposed_rate

public_sector

applied_at

outcome

outcome_at

2.6 Tabelle: rejection_reasons

Zweck:
Lernbasis für bessere Entscheidungen.

Standardisierte Codes:

BUDGET_TOO_LOW

TECH_STACK_MISMATCH

SENIORITY_MISMATCH

CLIENT_RISK

UNCLEAR_SCOPE

LOW_SUCCESS_PROBABILITY

PARALLEL_LIMIT_REACHED

3. Teamprofile & CV-Verarbeitung
3.1 Initialer Import

CVs manuell sammeln

Pfade definieren

Profile manuell strukturieren (einmalig)

3.2 Profiltext-Generierung

Aus CV ableiten:

Kurzprofil (5–7 Sätze)

Technologieliste

Branchenerfahrung

➡ Grundlage für Embeddings & Matcher

3.3 Embeddings

Modell: text-embedding-3-small

Nur bei:

Neuanlage

Profiländerung

4. Sourcing – Projektbeschaffung
4.1 Grundregeln

Jedes Portal eigener Scraper

Kein gemeinsamer Selector-Code

Fehler isoliert behandeln

4.2 Playwright-Setup

Headless

Timeout-Handling

Retry-Logik

optionale Proxies

4.3 Portale (Reihenfolge empfohlen)

bund.de

TED

freelancermap

GULP

Freelance.de

Malt

LinkedIn Jobs

Upwork

4.4 Normalisierung

Ziel:
Alle Projekte haben dieselbe Struktur, egal aus welcher Quelle.

Pflichtfelder:

title

description

source

external_id

url

5. Öffentlicher Sektor – Priorisierung
5.1 Erkennung

Quelle (bund.de, TED)

Keywords

Auftraggebertyp

5.2 Gewichtung

Bonus im Match-Score

Bevorzugung bei Parallelitätskonflikten

5.3 Stil-Anpassung

besonders sachlich

keine Marketing-Floskeln

Fokus auf:

Verlässlichkeit

Erfahrung

Dokumentation

6. KI-Analyse (CrewAI)
6.1 Agenten-Architektur

Researcher

Matcher

(optional später) Pricing-Agent

6.2 Researcher

Aufgaben:

Auftraggeber recherchieren

Webseite analysieren

Hinweise für Argumentation liefern

Output:

Branche

Stabilität

Tonalität

Besonderheiten

6.3 Matcher – Herzstück

Input:

Projekt

Research

Top-3 Profile (Embedding-Query)

Output (JSON):

match_score

empfohlene Person

Argumente

Risiken

Empfehlung: apply / reject

6.4 Ablehnungs-Intelligenz

Wenn reject:

reason_code

Erklärung

Erfolgswahrscheinlichkeit

7. Angebotsstrategie (Low-End, KI-gestützt)
7.1 Ziel

maximale Zuschlagswahrscheinlichkeit

kein Preisdumping

immer erklärbar

7.2 Regeln

Untere Marktgrenze

Harte Untergrenze pro Profil

Öffentlicher Sektor → konservativ

7.3 Speicherung

proposed_rate

rate_reasoning

8. Entscheidungslogik
8.1 Score-Thresholds

< 60 → automatisch ablehnen

60–74 → Review Queue

≥ 75 → Bewerbung möglich

8.2 Parallelitätskontrolle

Max. 8 aktive Bewerbungen

Aktive Status:

analyzed

matched

applied

9. Dokumentenerstellung
9.1 Ordnerstruktur
YYYY-MM-DD_Kunde_Projekt/

9.2 Anschreiben

Word-Template

Platzhalter

Argumente aus Matcher

9.3 CV-Handling

Nur passendes Profil

Keine Mehrfachprofile

10. Orchestrierung
10.1 Tagesablauf

Scraping

Dedupe

Embeddings

Research

Matching

Entscheidung

Dokumente

Logging

10.2 Scheduler

Cron

Fehler-tolerant

Wiederholbar

11. Review Queue
11.1 Zweck

Grenzfälle

Menschliche Entscheidung

Lernbasis

12. Analyse & Lernen (30 Tage)
12.1 KPIs

Response Rate

Interview Rate

Win Rate

Qualified Win Rate

12.2 Auswertungen

Portal

Öffentlicher Sektor

Match-Score

Angebotsniveau

Ablehnungsgründe

12.3 Ableitungen

Thresholds anpassen

Angebotsniveau feinjustieren

Ablehnungsregeln verschärfen

13. Logging & Monitoring

Scraper-Status

Fehler

KI-Kosten

Entscheidungen

14. Definition of Done

Kein Projekt ohne Entscheidung

Jede Ablehnung erklärbar

Erfolgsquote messbar

System lernt sichtbar

15. Langfristige Optionen (nach Stabilisierung)

UI (Streamlit)

Auto-Versand

Angebots-PDF

Multi-Language

Kundenhistorie