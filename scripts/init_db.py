"""
Database initialization script.

Creates all tables and optionally inserts a test project for verification.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import engine, SessionLocal
from app.db.models import Base, Project, TenderConfig, TenderLot, Client, TenderDecision


def init_database():
    """Create all database tables."""
    print("Creating database tables...")
    Base.metadata.create_all(engine)
    print("Tables created successfully.")


def verify_with_test_insert():
    """Insert and query a test project to verify the setup."""
    db = SessionLocal()
    try:
        # Check if test project already exists
        existing = db.query(Project).filter_by(
            source="test",
            external_id="verify-001"
        ).first()

        if existing:
            print(f"Test project already exists: {existing.title}")
            return True

        # Insert test project
        test_project = Project(
            source="test",
            external_id="verify-001",
            title="Test Project - Verification",
            description="This is a test project to verify database setup.",
            skills=["Python", "PostgreSQL"],
            public_sector=False,
            remote=True,
            status="new"
        )
        db.add(test_project)
        db.commit()
        print(f"Test project inserted with ID: {test_project.id}")

        # Query back
        queried = db.query(Project).filter_by(id=test_project.id).first()
        print(f"Queried back: {queried.title}")
        print(f"Skills: {queried.skills}")

        return True
    except Exception as e:
        print(f"Error during verification: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def create_default_tender_config():
    """Create default tender configuration if not exists."""
    db = SessionLocal()
    try:
        existing = db.query(TenderConfig).first()
        if existing:
            print("Tender config already exists.")
            return True

        config = TenderConfig(
            max_active_tenders=3,
            budget_min=50000,
            budget_max=250000,
            required_tech_keywords=[
                "webanwendung", "webapp", "webapplikation",
                "mobile app", "ios", "android", "flutter",
                "react", "vue", "angular", "frontend",
            ],
            excluded_keywords=[
                "sap", "oracle", "sharepoint",
                "hardware", "netzwerk", "infrastruktur",
            ],
        )
        db.add(config)
        db.commit()
        print(f"Created default tender config with ID: {config.id}")
        return True
    except Exception as e:
        print(f"Error creating tender config: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def list_tables():
    """List all tables in the database."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print("\nDatabase tables:")
    for table in sorted(tables):
        print(f"  - {table}")
    return tables


if __name__ == "__main__":
    init_database()
    print()

    # List tables
    tables = list_tables()

    # Verify new tender tables exist
    tender_tables = ["tender_config", "tender_lots", "clients", "tender_decisions"]
    missing = [t for t in tender_tables if t not in tables]
    if missing:
        print(f"\nWarning: Missing tender tables: {missing}")
    else:
        print("\nAll tender tables present.")

    print()
    if verify_with_test_insert():
        print("\nVerification successful! Database is ready.")
    else:
        print("\nVerification failed. Check your database connection.")

    # Create default tender config
    print()
    create_default_tender_config()
