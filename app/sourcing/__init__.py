"""Sourcing module - Portal scrapers and normalization."""

from app.sourcing.base import BaseScraper, RawProject
from app.sourcing.normalize import normalize_project, dedupe_projects, save_projects

__all__ = [
    "BaseScraper",
    "RawProject",
    "normalize_project",
    "dedupe_projects",
    "save_projects",
]
