# api/db.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

def _build_database_url() -> str:
    """
    Priority:
    1) If DATABASE_URL is provided, use it directly.
    2) Else if CLOUDSQL_CONNECTION_NAME is present, build a Cloud SQL Postgres socket URL.
    3) Else fallback to local SQLite.
    """
    direct = os.getenv("DATABASE_URL")
    if direct:
        return direct

    cloudsql = os.getenv("CLOUDSQL_CONNECTION_NAME")
    if cloudsql:
        user = os.getenv("DB_USER", "audituser")
        password = os.getenv("DB_PASSWORD", "")
        dbname = os.getenv("DB_NAME", "auditreadiness")

        # Cloud SQL Unix socket path in Cloud Run
        # IMPORTANT: password must not be empty
        return f"postgresql+psycopg2://{user}:{password}@/{dbname}?host=/cloudsql/{cloudsql}"

    # Local dev
    return "sqlite:///./app.db"


DATABASE_URL = _build_database_url()

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    # Postgres (Cloud SQL)
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},  # avoids hanging startup
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
