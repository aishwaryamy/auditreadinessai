from sqlalchemy.orm import Session
from .db import SessionLocal, engine
from .models import Control, Base


SEED_CONTROLS = [
    {
        "code": "CC6.1",
        "category": "Access Control",
        "title": "MFA enforced for critical systems",
        "description": "Multi-factor authentication is enabled for accounts with access to sensitive systems and data.",
    },
    {
        "code": "CC6.2",
        "category": "Access Control",
        "title": "User access provisioning and deprovisioning",
        "description": "Access is granted based on role and removed promptly upon termination or role change.",
    },
    {
        "code": "CC6.3",
        "category": "Access Control",
        "title": "Periodic access review",
        "description": "Access rights are reviewed on a defined schedule (e.g., quarterly) and changes are documented.",
    },
    {
        "code": "CC8.1",
        "category": "Change Management",
        "title": "Code changes require pull request review",
        "description": "Changes to production code are reviewed and approved before merge/deploy.",
    },
    {
        "code": "CC8.2",
        "category": "Change Management",
        "title": "Production changes are logged",
        "description": "Deployments and production changes are tracked with timestamps and responsible parties.",
    },
]


def seed_controls(db: Session) -> None:
    for item in SEED_CONTROLS:
        exists = db.query(Control).filter(Control.code == item["code"]).first()
        if not exists:
            db.add(Control(**item))
    db.commit()


def main() -> None:
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_controls(db)
        print("Seed complete: controls inserted/verified.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
