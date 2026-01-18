from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import os
from datetime import datetime

from .db import SessionLocal, engine
from .models import Base, Control, Artifact

app = FastAPI(title="AuditReadinessAI")

Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    saved_name = f"{ts}_{safe_name}"
    save_path = os.path.join(UPLOAD_DIR, saved_name)

    contents = await file.read()
    with open(save_path, "wb") as f:
        f.write(contents)

    # Store metadata in DB
    db = SessionLocal()
    try:
        artifact = Artifact(
            source=source,
            name=file.filename,
            uri=save_path,
        )
        db.add(artifact)
        db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/artifacts", status_code=303)
