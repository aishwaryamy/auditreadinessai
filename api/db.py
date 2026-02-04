# api/db.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Base lives here so models can import it safely
Base = declarative_base()

# If DATABASE_URL is set (Cloud Run / Cloud SQL), use it.
# Otherwise fall back to local SQLite.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Local dev SQLite
    DATABASE_URL = "sqlite:///./app.db"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    # Postgres on Cloud Run/Cloud SQL
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},  # prevents hanging startup
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
