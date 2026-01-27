"""Initialize team members in database with embeddings."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.session import SessionLocal
from app.db.models import TeamMember
from app.team.profile_loader import parse_team_profiles_md
from app.team.embedding import create_embedding


def init_team_members():
    """Load team profiles and store in database with embeddings."""
    print("Parsing team profiles from Markdown...")
    profiles = parse_team_profiles_md()
    print(f"Found {len(profiles)} team profiles")

    db = SessionLocal()
    try:
        for profile in profiles:
            # Check if member already exists
            existing = db.query(TeamMember).filter(
                TeamMember.name == profile.name
            ).first()

            if existing:
                print(f"  Updating existing profile: {profile.name}")
                member = existing
            else:
                print(f"  Creating new profile: {profile.name}")
                member = TeamMember(name=profile.name)
                db.add(member)

            # Update fields
            member.role = profile.role
            member.seniority = "Senior" if profile.years_experience >= 5 else "Mid"
            member.skills = profile.skills
            member.industries = profile.industries
            member.languages = profile.languages
            member.years_experience = profile.years_experience
            member.min_hourly_rate = profile.min_hourly_rate
            member.cv_path = f"cvs/{profile.cv_filename}" if profile.cv_filename else None
            member.profile_text = profile.profile_text
            member.active = True

            # Generate embedding
            print(f"    Generating embedding for {profile.name}...")
            embedding = create_embedding(profile.profile_text)
            member.profile_embedding = embedding

            db.commit()
            print(f"    Saved: {profile.name} (ID: {member.id})")

        # Verify
        count = db.query(TeamMember).filter(TeamMember.active == True).count()
        print(f"\nTotal active team members in DB: {count}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_team_members()
