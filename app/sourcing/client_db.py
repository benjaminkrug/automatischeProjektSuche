"""Client database management for tender pipeline.

Manages contracting authorities (Vergabestellen) history for learning
and improved scoring.
"""

import re
from typing import List, Optional, Tuple
from datetime import datetime
import logging

from sqlalchemy.orm import Session

from app.db.models import Client, Project

logger = logging.getLogger(__name__)


def normalize_client_name(name: str) -> str:
    """Normalize client name for matching.

    Args:
        name: Raw client name

    Returns:
        Normalized name (lowercase, cleaned)
    """
    if not name:
        return ""

    # Lowercase
    normalized = name.lower()

    # Remove common suffixes
    suffixes = [
        "gmbh", "ag", "kg", "ohg", "e.v.", "ev", "e.g.", "eg",
        "mbh", "ug", "gbr", "kgaa", "se",
        "bundesamt", "ministerium", "landesamt", "stadt", "kommune",
        "behörde", "amt", "verwaltung",
    ]
    for suffix in suffixes:
        normalized = re.sub(rf"\s*{suffix}\s*", " ", normalized)

    # Remove extra whitespace
    normalized = " ".join(normalized.split())

    return normalized.strip()


def find_client(db: Session, client_name: str) -> Optional[Client]:
    """Find a client by name or alias.

    Args:
        db: Database session
        client_name: Client name to search for

    Returns:
        Client if found, None otherwise
    """
    if not client_name:
        return None

    normalized = normalize_client_name(client_name)

    # Try exact name match first
    client = db.query(Client).filter(
        Client.name.ilike(f"%{normalized}%")
    ).first()

    if client:
        return client

    # Try aliases - use any() for PostgreSQL ARRAY
    try:
        client = db.query(Client).filter(
            Client.aliases.any(normalized)
        ).first()
    except Exception:
        # Fallback: manual iteration if array query fails
        all_clients = db.query(Client).filter(Client.aliases.isnot(None)).all()
        for c in all_clients:
            if c.aliases and normalized in c.aliases:
                return c
        return None

    return client


def get_or_create_client(
    db: Session,
    client_name: str,
    sector: Optional[str] = None,
) -> Client:
    """Get existing client or create new one.

    Args:
        db: Database session
        client_name: Client name
        sector: Optional sector classification

    Returns:
        Client instance
    """
    client = find_client(db, client_name)

    if client:
        # Update sector if provided and not set
        if sector and not client.sector:
            client.sector = sector
            db.commit()
        return client

    # Create new client
    client = Client(
        name=client_name,
        aliases=[normalize_client_name(client_name)],
        sector=sector or detect_sector(client_name),
        tenders_seen=0,
        tenders_applied=0,
        tenders_won=0,
    )
    db.add(client)
    db.commit()

    logger.info(f"Created new client: {client_name}")
    return client


def detect_sector(client_name: str) -> str:
    """Detect sector from client name.

    Args:
        client_name: Client name

    Returns:
        Sector classification
    """
    name_lower = client_name.lower()

    # Federal level
    if any(kw in name_lower for kw in [
        "bundesamt", "bundesministerium", "bundesanstalt",
        "bundesagentur", "bundesrepublik", "bund",
    ]):
        return "bund"

    # State level
    if any(kw in name_lower for kw in [
        "landesamt", "landesministerium", "land ",
        "freistaat", "landeshauptstadt",
    ]):
        return "land"

    # Municipal level
    if any(kw in name_lower for kw in [
        "stadt ", "gemeinde", "kommune", "kreis",
        "landkreis", "bezirk", "stadtverwaltung",
    ]):
        return "kommune"

    # EU level
    if any(kw in name_lower for kw in [
        "europäische", "european", "eu ", "kommission",
    ]):
        return "eu"

    return "unknown"


def increment_tender_seen(db: Session, client: Client) -> None:
    """Increment the tenders_seen counter for a client.

    Args:
        db: Database session
        client: Client instance
    """
    client.tenders_seen = (client.tenders_seen or 0) + 1
    client.updated_at = datetime.utcnow()
    db.commit()


def record_application(
    db: Session,
    client: Client,
    won: Optional[bool] = None,
) -> None:
    """Record an application to a client's tender.

    Args:
        db: Database session
        client: Client instance
        won: Whether the application was won (None if unknown)
    """
    client.tenders_applied = (client.tenders_applied or 0) + 1

    if won is True:
        client.tenders_won = (client.tenders_won or 0) + 1

    # Recalculate win rate
    if client.tenders_applied > 0:
        client.win_rate = (client.tenders_won or 0) / client.tenders_applied

    client.updated_at = datetime.utcnow()
    db.commit()


def update_outcome(
    db: Session,
    client: Client,
    won: bool,
) -> None:
    """Update outcome for a previously recorded application.

    Args:
        db: Database session
        client: Client instance
        won: Whether the tender was won
    """
    if won:
        client.tenders_won = (client.tenders_won or 0) + 1

    # Recalculate win rate
    if client.tenders_applied > 0:
        client.win_rate = (client.tenders_won or 0) / client.tenders_applied

    client.updated_at = datetime.utcnow()
    db.commit()


def set_client_rating(
    db: Session,
    client: Client,
    payment_rating: Optional[int] = None,
    communication_rating: Optional[int] = None,
    notes: Optional[str] = None,
) -> None:
    """Set rating for a client.

    Args:
        db: Database session
        client: Client instance
        payment_rating: Payment rating (1-5)
        communication_rating: Communication rating (1-5)
        notes: Additional notes
    """
    if payment_rating is not None:
        if 1 <= payment_rating <= 5:
            client.payment_rating = payment_rating
        else:
            raise ValueError("Rating must be between 1 and 5")

    if communication_rating is not None:
        if 1 <= communication_rating <= 5:
            client.communication_rating = communication_rating
        else:
            raise ValueError("Rating must be between 1 and 5")

    if notes is not None:
        client.notes = notes

    client.updated_at = datetime.utcnow()
    db.commit()


def add_client_alias(db: Session, client: Client, alias: str) -> None:
    """Add an alias for a client.

    Args:
        db: Database session
        client: Client instance
        alias: Alias to add
    """
    aliases = client.aliases or []
    normalized_alias = normalize_client_name(alias)

    if normalized_alias not in aliases:
        aliases.append(normalized_alias)
        client.aliases = aliases
        client.updated_at = datetime.utcnow()
        db.commit()


def add_contact(
    db: Session,
    client: Client,
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    role: Optional[str] = None,
) -> None:
    """Add a contact for a client.

    Args:
        db: Database session
        client: Client instance
        name: Contact name
        email: Contact email
        phone: Contact phone
        role: Contact role
    """
    contacts = client.known_contacts or []

    contact = {
        "name": name,
        "email": email,
        "phone": phone,
        "role": role,
    }

    # Check for duplicates by email
    if email:
        for existing in contacts:
            if existing.get("email") == email:
                # Update existing
                existing.update(contact)
                client.known_contacts = contacts
                client.updated_at = datetime.utcnow()
                db.commit()
                return

    contacts.append(contact)
    client.known_contacts = contacts
    client.updated_at = datetime.utcnow()
    db.commit()


def get_top_clients(
    db: Session,
    limit: int = 10,
    min_applications: int = 1,
) -> List[Client]:
    """Get top clients by win rate.

    Args:
        db: Database session
        limit: Maximum number of clients to return
        min_applications: Minimum number of applications

    Returns:
        List of top clients
    """
    return db.query(Client).filter(
        Client.tenders_applied >= min_applications,
        Client.win_rate.isnot(None),
    ).order_by(
        Client.win_rate.desc()
    ).limit(limit).all()


def get_client_stats(db: Session) -> dict:
    """Get overall client statistics.

    Args:
        db: Database session

    Returns:
        Dictionary with statistics
    """
    total_clients = db.query(Client).count()
    active_clients = db.query(Client).filter(
        Client.tenders_applied > 0
    ).count()

    total_seen = db.query(Client).with_entities(
        db.func.sum(Client.tenders_seen)
    ).scalar() or 0

    total_applied = db.query(Client).with_entities(
        db.func.sum(Client.tenders_applied)
    ).scalar() or 0

    total_won = db.query(Client).with_entities(
        db.func.sum(Client.tenders_won)
    ).scalar() or 0

    return {
        "total_clients": total_clients,
        "active_clients": active_clients,
        "total_tenders_seen": total_seen,
        "total_applications": total_applied,
        "total_won": total_won,
        "overall_win_rate": total_won / total_applied if total_applied > 0 else 0,
    }


def get_client_for_project(db: Session, project: Project) -> Tuple[Optional[Client], dict]:
    """Get client info for a project with scoring data.

    Args:
        db: Database session
        project: Project instance

    Returns:
        Tuple of (Client or None, scoring_data dict)
    """
    if not project.client_name:
        return None, {
            "win_rate": None,
            "tenders_applied": 0,
            "payment_rating": None,
        }

    client = find_client(db, project.client_name)

    if not client:
        return None, {
            "win_rate": None,
            "tenders_applied": 0,
            "payment_rating": None,
        }

    return client, {
        "win_rate": client.win_rate,
        "tenders_applied": client.tenders_applied or 0,
        "payment_rating": client.payment_rating,
    }
