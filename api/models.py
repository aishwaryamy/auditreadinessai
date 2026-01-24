from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .db import Base


class Control(Base):
    __tablename__ = "controls"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)  # e.g., CC6.1
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)  # Access Control, Change Mgmt, etc.

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False)  # "github" or "upload"
    name = Column(String(255), nullable=False)
    uri = Column(Text, nullable=True)  # later: Cloud Storage path / GitHub URL
    collected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    control_id = Column(Integer, ForeignKey("controls.id"), nullable=False)
    status = Column(String(30), nullable=False, default="created")  # created/running/done/failed
    notes = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    control = relationship("Control")

from sqlalchemy import Boolean, Float

class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id = Column(Integer, primary_key=True, index=True)
    control_id = Column(Integer, ForeignKey("controls.id"), nullable=False)
    text = Column(String(300), nullable=False)
    required = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    control = relationship("Control")


class ControlArtifactLink(Base):
    __tablename__ = "control_artifact_links"

    id = Column(Integer, primary_key=True, index=True)
    control_id = Column(Integer, ForeignKey("controls.id"), nullable=False)
    artifact_id = Column(Integer, ForeignKey("artifacts.id"), nullable=False)

    linked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    control = relationship("Control")
    artifact = relationship("Artifact")


class ControlScore(Base):
    __tablename__ = "control_scores"

    id = Column(Integer, primary_key=True, index=True)
    control_id = Column(Integer, ForeignKey("controls.id"), nullable=False)

    coverage_pct = Column(Float, nullable=False)
    freshness_score = Column(Float, nullable=False)
    source_credibility = Column(Float, nullable=False)
    readiness_score = Column(Float, nullable=False)

    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    control = relationship("Control")


class Gap(Base):
    __tablename__ = "gaps"

    id = Column(Integer, primary_key=True, index=True)
    control_id = Column(Integer, ForeignKey("controls.id"), nullable=False)

    severity = Column(String(20), nullable=False)  # Low/Med/High
    reason = Column(String(300), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    control = relationship("Control")
