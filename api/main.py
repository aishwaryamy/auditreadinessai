from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import SessionLocal, engine
from .models import Base, Control

app = FastAPI(title="AuditReadinessAI")

# Create tables on startup (simple for beginners; later we’ll use migrations)
Base.metadata.create_all(bind=engine)

# Static files + templates (UI)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


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
