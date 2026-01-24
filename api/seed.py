from sqlalchemy.orm import Session
from .db import SessionLocal, engine
from .models import Base, Control, ChecklistItem


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

SEED_CHECKLIST = {
    "CC6.1": [
        "Evidence of MFA enforcement (export/screenshot/config report)",
        "List of users/groups covered by MFA policy",
        "Date range of evidence within last 90 days",
    ],
    "CC6.2": [
        "Documented onboarding/offboarding procedure",
        "Recent example of access granted with approval",
        "Recent example of access removed after termination/change",
    ],
    "CC6.3": [
        "Access review report/export for last quarter",
        "List of reviewers and approvals/sign-off",
        "Remediation actions documented for exceptions",
    ],
    "CC8.1": [
        "Branch protection or PR review settings (repo config evidence)",
        "Sample PRs showing reviews before merge (last 90 days)",
        "Evidence of required reviewers/CODEOWNERS (if used)",
    ],
    "CC8.2": [
        "Deployment or change log with timestamps (last 90 days)",
        "Evidence of who deployed/approved changes",
        "Link between deploys and PRs/releases (if available)",
    ],
}


def seed_controls(db: Session) -> None:
    for item in SEED_CONTROLS:
        exists = db.query(Control).filter(Control.code == item["code"]).first()
        if not exists:
            db.add(Control(**item))
    db.commit()


def seed_checklist_items(db: Session) -> None:
    for control in db.query(Control).all():
        items = SEED_CHECKLIST.get(control.code, [])
        for text in items:
            exists = (
                db.query(ChecklistItem)
                .filter(
                    ChecklistItem.control_id == control.id,
                    ChecklistItem.text == text,
                )
                .first()
            )
            if not exists:
                db.add(ChecklistItem(control_id=control.id, text=text, required=True))
    db.commit()


def main() -> None:
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_controls(db)
        seed_checklist_items(db)
        print("Seed complete: controls + checklist inserted/verified.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
