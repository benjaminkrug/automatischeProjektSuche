"""
Database initialization script.

Creates all tables and optionally inserts a test project for verification.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import engine, SessionLocal
from app.db.models import Base, Project


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


if __name__ == "__main__":
    init_database()
    print()
    if verify_with_test_insert():
        print("\nVerification successful! Database is ready.")
    else:
        print("\nVerification failed. Check your database connection.")
