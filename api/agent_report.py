# api/agent_report.py

import os
import logging
from dotenv import load_dotenv
from openai import OpenAI

from .db import SessionLocal
from .models import Control, ChecklistItem, ArtifactChunk, Artifact
from .retrieval import hybrid_retrieve, keyword_retrieve

load_dotenv()  # loads .env if present
logger = logging.getLogger(__name__)


def _build_prompt(control, checklist_items, artifacts_with_snippets):
    checklist_text = (
        "\n".join([f"- {it.text}" for it in checklist_items])
        or "- (no checklist items found)"
    )

    evidence_blocks = []
    for a, snippets in artifacts_with_snippets:
        joined = "\n\n".join([f"Snippet {i+1}: {s}" for i, s in enumerate(snippets)])
        evidence_blocks.append(
            f"[Artifact {a.id}] name={a.name} source={a.source}\n{joined}"
        )

    evidence_text = (
        "\n\n".join(evidence_blocks)
        if evidence_blocks
        else "(No evidence snippets available.)"
    )

    return f"""
You are an audit/compliance assistant. Write an SOC 2 evidence narrative for ONE control.

Rules:
- Use ONLY the evidence snippets provided.
- Do NOT invent facts. If evidence is missing, say "Missing evidence" and list what to collect.
- Every factual claim must include a citation like [Artifact 10].
- Output must be concise and structured.

Control:
- Code: {control.code}
- Title: {control.title}
- Description: {control.description}

Checklist (what evidence auditors expect):
{checklist_text}

Evidence snippets:
{evidence_text}

Write the report with these sections:
1) Summary (2–4 sentences)
2) Evidence mapped to checklist (bullet list; each bullet has citations)
3) Gaps / Missing evidence (bullet list)
4) Next best actions (3 bullets)
""".strip()


def _pick_best_artifacts_for_item(item_text: str, artifacts_with_snippets, top_n: int = 2):
    """
    Deterministic scoring:
    - +2 if item keywords appear in artifact name
    - +1 if keywords appear in snippet text
    """
    keywords = [
        w.lower()
        for w in item_text.replace("/", " ").replace("(", " ").replace(")", " ").split()
        if len(w) >= 4
    ]

    scored = []
    for a, snippets in artifacts_with_snippets:
        hay_name = (a.name or "").lower()
        hay_text = "\n".join(snippets).lower()

        score = 0
        for kw in keywords:
            if kw in hay_name:
                score += 2
            if kw in hay_text:
                score += 1

        scored.append((score, a.id))

    scored.sort(reverse=True)  # highest score first
    best = [aid for score, aid in scored if score > 0][:top_n]
    return best


def _fallback_report(control, checklist_items, artifacts_with_snippets, reason: str = "") -> str:
    """
    Deterministic fallback when LLM call fails or retrieval fails.
    Always returns a readable report (never raises).
    """
    header_reason = f" Reason: {reason}" if reason else ""

    lines = []
    lines.append("1) Summary")
    lines.append(
        "LLM generation is currently unavailable or retrieval failed. "
        "This is a deterministic evidence narrative generated from retrieved snippets."
        + header_reason
    )
    lines.append(f"Control: {control.code} — {control.title}")
    lines.append("")

    lines.append("2) Evidence mapped to checklist")
    if not checklist_items:
        lines.append("- (No checklist items found)")
    else:
        for it in checklist_items:
            if not artifacts_with_snippets:
                lines.append(f"- {it.text} — Missing evidence")
                continue

            best_ids = _pick_best_artifacts_for_item(it.text, artifacts_with_snippets, top_n=2)
            if best_ids:
                citations = ", ".join([f"[Artifact {aid}]" for aid in best_ids])
                lines.append(f"- {it.text} — Candidate evidence: {citations}")
            else:
                lines.append(f"- {it.text} — Missing evidence (no strong match found in retrieved snippets)")

    lines.append("")
    lines.append("3) Gaps / Missing evidence")
    if not artifacts_with_snippets:
        lines.append("- No indexed evidence snippets found. Upload text evidence (.txt/.md/.csv) first.")
    else:
        lines.append("- Confirm each checklist item has direct proof (exports/logs/screenshots) and is within the last 90 days.")
        lines.append("- If any checklist item lacks direct evidence, add an artifact that proves it and re-run.")

    lines.append("")
    lines.append("4) Next best actions")
    lines.append("- Upload 1–2 more artifacts that directly prove this control (exports/logs/policies).")
    lines.append("- Link the best artifacts to the control and click “Compute readiness”.")
    lines.append("- Re-run retrieval evaluation after adding more labeled pairs.")

    return "\n".join(lines)


def _safe_get_artifact_ids(control_id: int, k_artifacts: int) -> list[int]:
    """
    Never throws. If hybrid fails (HF 429 / model download issues / etc),
    falls back to keyword retrieval.
    """
    try:
        artifact_ids = hybrid_retrieve(control_id, k=k_artifacts)
    except Exception as e:
        logger.exception("hybrid_retrieve failed: %s", str(e))
        artifact_ids = []

    if not artifact_ids:
        try:
            artifact_ids = keyword_retrieve(control_id, k=k_artifacts)
        except Exception as e:
            logger.exception("keyword_retrieve failed: %s", str(e))
            artifact_ids = []

    return artifact_ids


def generate_control_report(control_id: int, k_artifacts: int = 5, snippets_per_artifact: int = 2):
    """
    Returns: (report_text, mode)
      mode = "openai" or "fallback"
    This function should NEVER raise (so your FastAPI route won't 500).
    """
    model = os.getenv("OPENAI_MODEL", "gpt-5.2")
    client = OpenAI()

    db = SessionLocal()
    try:
        control = db.query(Control).filter(Control.id == control_id).first()
        if not control:
            return "Control not found.", "fallback"

        checklist_items = (
            db.query(ChecklistItem)
            .filter(ChecklistItem.control_id == control_id)
            .all()
        )

        # 1) Retrieve artifacts safely (never throw)
        artifact_ids = _safe_get_artifact_ids(control_id, k_artifacts)

        # 2) Build artifacts_with_snippets (also never throw)
        artifacts_with_snippets = []
        try:
            for aid in artifact_ids:
                a = db.query(Artifact).filter(Artifact.id == aid).first()
                if not a:
                    continue

                chunks = (
                    db.query(ArtifactChunk)
                    .filter(ArtifactChunk.artifact_id == aid)
                    .order_by(ArtifactChunk.chunk_index.asc())
                    .limit(snippets_per_artifact)
                    .all()
                )
                snippets = [(c.text or "")[:1200] for c in chunks]
                artifacts_with_snippets.append((a, snippets))
        except Exception as e:
            logger.exception("Failed building snippets: %s", str(e))
            # Still allow report generation; it will show missing evidence.

        prompt = _build_prompt(control, checklist_items, artifacts_with_snippets)

        # 3) OpenAI call — if it fails, return deterministic fallback (not 500)
        try:
            resp = client.responses.create(model=model, input=prompt)
            return resp.output_text, "openai"
        except Exception as e:
            logger.exception("OpenAI report generation failed: %s", str(e))
            return _fallback_report(control, checklist_items, artifacts_with_snippets, reason=str(e)), "fallback"

    except Exception as e:
        # Absolute last-resort guardrail: NEVER 500
        logger.exception("generate_control_report unexpected error: %s", str(e))
        # We might not have control loaded if this happens early
        return "Agent report failed unexpectedly. Try again after uploading evidence.", "fallback"
    finally:
        db.close()
