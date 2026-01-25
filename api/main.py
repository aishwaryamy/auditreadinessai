# api/main.py

import os
from datetime import datetime, timezone

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import SessionLocal, engine
from .models import (
    Base,
    Control,
    Artifact,
    ChecklistItem,
    ControlArtifactLink,
    ControlScore,
    Gap,
    ArtifactChunk,
)
from .indexing import read_text_from_file, chunk_text
from .agent_report import generate_control_report


# ----------------------------
# App + Startup Setup
# ----------------------------
app = FastAPI(title="AuditReadinessAI")

Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ----------------------------
# Utility: Scoring
# ----------------------------
def compute_scores(linked_artifacts, checklist_count: int):
    # Coverage
    if checklist_count <= 0:
        coverage_pct = 0.0
    else:
        coverage_pct = min(100.0, (len(linked_artifacts) / checklist_count) * 100.0)

    # Freshness
    freshness_score = 0.0
    if linked_artifacts:
        # Find newest collected_at
        newest = max(
            (a.collected_at for a in linked_artifacts if a.collected_at is not None),
            default=None,
        )
        if newest is not None:
            # Make both naive to avoid SQLite tz issues
            now = datetime.utcnow()
            newest_naive = newest.replace(tzinfo=None) if newest.tzinfo is not None else newest
            age_days = (now - newest_naive).days

            if age_days <= 90:
                freshness_score = 100.0
            elif age_days <= 180:
                freshness_score = 50.0
            else:
                freshness_score = 0.0

    # Source credibility
    if not linked_artifacts:
        source_credibility = 0.0
    else:
        weights = []
        for a in linked_artifacts:
            # You can later add more sources (gcp/github/slack etc.)
            weights.append(1.0 if a.source == "github" else 0.7)
        source_credibility = (sum(weights) / len(weights)) * 100.0

    # Final readiness score (weighted)
    readiness_score = 0.5 * coverage_pct + 0.3 * freshness_score + 0.2 * source_credibility
    return coverage_pct, freshness_score, source_credibility, readiness_score


# ----------------------------
# Health + Home
# ----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    db = SessionLocal()
    try:
        controls = db.query(Control).order_by(Control.category, Control.code).all()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "controls": controls},
        )
    finally:
        db.close()


# ----------------------------
# Artifacts
# ----------------------------
@app.get("/artifacts", response_class=HTMLResponse)
def artifacts_page(request: Request):
    db = SessionLocal()
    try:
        artifacts = db.query(Artifact).order_by(Artifact.collected_at.desc()).all()
        return templates.TemplateResponse(
            "artifacts.html",
            {"request": request, "artifacts": artifacts},
        )
    finally:
        db.close()


@app.post("/artifacts/upload")
async def upload_artifact(
    file: UploadFile = File(...),
    source: str = Form("upload"),
):
    # Save file locally
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = (file.filename or "upload").replace("/", "_").replace("\\", "_")
    saved_name = f"{ts}_{safe_name}"
    save_path = os.path.join(UPLOAD_DIR, saved_name)

    contents = await file.read()
    with open(save_path, "wb") as f:
        f.write(contents)

    # Store metadata in DB + index chunks
    db = SessionLocal()
    try:
        artifact = Artifact(
            source=source,
            name=file.filename,
            uri=save_path,
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)

        # Index chunks (text only for now)
        text = read_text_from_file(save_path)
        chunks = chunk_text(text)

        for i, ch in enumerate(chunks):
            db.add(ArtifactChunk(artifact_id=artifact.id, chunk_index=i, text=ch))

        db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/artifacts", status_code=303)


# ----------------------------
# Controls
# ----------------------------
@app.get("/controls/{control_id}", response_class=HTMLResponse)
def control_detail(request: Request, control_id: int):
    db = SessionLocal()
    try:
        control = db.query(Control).filter(Control.id == control_id).first()
        if not control:
            return HTMLResponse("Control not found", status_code=404)

        checklist = (
            db.query(ChecklistItem)
            .filter(ChecklistItem.control_id == control_id)
            .order_by(ChecklistItem.id.asc())
            .all()
        )

        links = db.query(ControlArtifactLink).filter(ControlArtifactLink.control_id == control_id).all()
        linked_artifacts = [
            db.query(Artifact).filter(Artifact.id == l.artifact_id).first()
            for l in links
        ]
        linked_artifacts = [a for a in linked_artifacts if a is not None]

        all_artifacts = db.query(Artifact).order_by(Artifact.collected_at.desc()).all()

        latest_score = (
            db.query(ControlScore)
            .filter(ControlScore.control_id == control_id)
            .order_by(ControlScore.computed_at.desc())
            .first()
        )

        gaps = (
            db.query(Gap)
            .filter(Gap.control_id == control_id, Gap.resolved_at.is_(None))
            .order_by(Gap.created_at.desc())
            .all()
        )

        return templates.TemplateResponse(
            "control_detail.html",
            {
                "request": request,
                "control": control,
                "checklist": checklist,
                "linked": linked_artifacts,
                "all_artifacts": all_artifacts,
                "latest_score": latest_score,
                "gaps": gaps,
            },
        )
    finally:
        db.close()


@app.post("/controls/{control_id}/link-artifact")
def link_artifact(control_id: int, artifact_id: int = Form(...)):
    db = SessionLocal()
    try:
        exists = (
            db.query(ControlArtifactLink)
            .filter(
                ControlArtifactLink.control_id == control_id,
                ControlArtifactLink.artifact_id == artifact_id,
            )
            .first()
        )
        if not exists:
            db.add(ControlArtifactLink(control_id=control_id, artifact_id=artifact_id))
            db.commit()

        return RedirectResponse(url=f"/controls/{control_id}", status_code=303)
    finally:
        db.close()


@app.post("/controls/{control_id}/compute-score")
def compute_score(control_id: int):
    db = SessionLocal()
    try:
        checklist_count = db.query(ChecklistItem).filter(ChecklistItem.control_id == control_id).count()

        links = db.query(ControlArtifactLink).filter(ControlArtifactLink.control_id == control_id).all()
        linked_artifacts = [
            db.query(Artifact).filter(Artifact.id == l.artifact_id).first()
            for l in links
        ]
        linked_artifacts = [a for a in linked_artifacts if a is not None]

        coverage_pct, freshness_score, source_credibility, readiness_score = compute_scores(
            linked_artifacts, checklist_count
        )

        db.add(
            ControlScore(
                control_id=control_id,
                coverage_pct=coverage_pct,
                freshness_score=freshness_score,
                source_credibility=source_credibility,
                readiness_score=readiness_score,
            )
        )

        # Resolve previous unresolved gaps for this control (avoid duplicates)
        db.query(Gap).filter(
            Gap.control_id == control_id,
            Gap.resolved_at.is_(None),
        ).update({Gap.resolved_at: datetime.now(timezone.utc).replace(tzinfo=None)})

        # Add current gaps (based on latest computed state)
        if coverage_pct < 100.0:
            db.add(Gap(control_id=control_id, severity="High", reason="Missing evidence: coverage below 100%"))
        if freshness_score < 100.0:
            db.add(Gap(control_id=control_id, severity="Medium", reason="Evidence may be stale (older than 90 days)"))
        if source_credibility < 80.0 and linked_artifacts:
            db.add(Gap(control_id=control_id, severity="Low", reason="Evidence relies heavily on manual uploads vs system sources"))

        db.commit()
        return RedirectResponse(url=f"/controls/{control_id}", status_code=303)
    finally:
        db.close()


# ----------------------------
# Agent Report (OpenAI)
# ----------------------------
@app.post("/controls/{control_id}/agent-report", response_class=HTMLResponse)
def agent_report(control_id: int, request: Request):
    db = SessionLocal()
    try:
        control = db.query(Control).filter(Control.id == control_id).first()
        if not control:
            return HTMLResponse("Control not found", status_code=404)

        report, mode = generate_control_report(control_id)

        return templates.TemplateResponse(
            "agent_report.html",
            {"request": request, "control": control, "report": report, "mode": mode},
        )
    finally:
        db.close()


