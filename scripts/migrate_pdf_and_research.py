"""
Database migration for PDF analysis and client research features.

Adds:
- pdf_text, pdf_count columns to projects table
- client_research_cache table

Run with: python scripts/migrate_pdf_and_research.py
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import engine, SessionLocal
from app.db.models import Base


def check_column_exists(db, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    result = db.execute(text(f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = :table AND column_name = :column
    """), {"table": table, "column": column})
    return result.fetchone() is not None


def check_table_exists(db, table: str) -> bool:
    """Check if a table exists."""
    result = db.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_name = :table
    """), {"table": table})
    return result.fetchone() is not None


def migrate_projects_table(db):
    """Add PDF columns to projects table."""
    print("Checking projects table...")

    # Add pdf_text column
    if not check_column_exists(db, "projects", "pdf_text"):
        print("  Adding pdf_text column...")
        db.execute(text("ALTER TABLE projects ADD COLUMN pdf_text TEXT"))
        print("  Added pdf_text column.")
    else:
        print("  pdf_text column already exists.")

    # Add pdf_count column
    if not check_column_exists(db, "projects", "pdf_count"):
        print("  Adding pdf_count column...")
        db.execute(text("ALTER TABLE projects ADD COLUMN pdf_count INTEGER DEFAULT 0"))
        print("  Added pdf_count column.")
    else:
        print("  pdf_count column already exists.")

    db.commit()


def migrate_client_research_cache(db):
    """Create client_research_cache table."""
    print("Checking client_research_cache table...")

    if check_table_exists(db, "client_research_cache"):
        print("  client_research_cache table already exists.")
        return

    print("  Creating client_research_cache table...")
    db.execute(text("""
        CREATE TABLE client_research_cache (
            id SERIAL PRIMARY KEY,
            client_name_normalized VARCHAR(255) UNIQUE NOT NULL,
            company_website TEXT,
            company_about_text TEXT,
            hrb_number VARCHAR(50),
            founding_year INTEGER,
            employee_count VARCHAR(50),
            kununu_rating FLOAT,
            last_updated TIMESTAMP DEFAULT NOW()
        )
    """))
    print("  Created client_research_cache table.")

    # Create index on normalized name
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_client_research_name
        ON client_research_cache (client_name_normalized)
    """))
    print("  Created index on client_name_normalized.")

    db.commit()


def run_migration():
    """Run all migrations."""
    print("=" * 50)
    print("PDF & Client Research Migration")
    print("=" * 50)
    print()

    db = SessionLocal()
    try:
        migrate_projects_table(db)
        print()
        migrate_client_research_cache(db)
        print()
        print("=" * 50)
        print("Migration completed successfully!")
        print("=" * 50)
        return True
    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def verify_migration():
    """Verify the migration was successful."""
    print()
    print("Verifying migration...")

    db = SessionLocal()
    try:
        # Check projects columns
        assert check_column_exists(db, "projects", "pdf_text"), "pdf_text missing"
        assert check_column_exists(db, "projects", "pdf_count"), "pdf_count missing"
        print("  projects table: OK")

        # Check client_research_cache table
        assert check_table_exists(db, "client_research_cache"), "table missing"
        print("  client_research_cache table: OK")

        print()
        print("Verification successful!")
        return True
    except AssertionError as e:
        print(f"Verification failed: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = run_migration()
    if success:
        verify_migration()
    else:
        sys.exit(1)
