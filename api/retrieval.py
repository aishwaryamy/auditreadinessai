# api/retrieval.py

import os
import logging
from typing import Optional, List, Tuple, Dict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .db import SessionLocal
from .models import Control, ChecklistItem, ArtifactChunk

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Query construction
# -----------------------------------------------------------------------------
def control_query_text(db, control_id: int) -> str:
    c = db.query(Control).filter(Control.id == control_id).first()
    if not c:
        return ""

    items = db.query(ChecklistItem).filter(ChecklistItem.control_id == control_id).all()
    parts = [c.code, c.title, c.description] + [it.text for it in items]
    return " ".join([p for p in parts if p])


# -----------------------------------------------------------------------------
# Chunk loading
# -----------------------------------------------------------------------------
def load_chunks(db) -> List[Tuple[int, int, str]]:
    """
    Returns list of (chunk_id, artifact_id, text)
    """
    rows = db.query(ArtifactChunk).all()
    return [(r.id, r.artifact_id, r.text or "") for r in rows]


# -----------------------------------------------------------------------------
# Keyword retrieval (TF-IDF)
# -----------------------------------------------------------------------------
def keyword_retrieve(control_id: int, k: int = 10) -> List[int]:
    db = SessionLocal()
    try:
        query = control_query_text(db, control_id).strip()
        if not query:
            return []

        chunks = load_chunks(db)
        if not chunks:
            return []

        chunk_texts = [t for _, _, t in chunks]

        vectorizer = TfidfVectorizer(stop_words="english")
        X = vectorizer.fit_transform(chunk_texts)
        q = vectorizer.transform([query])

        sims = cosine_similarity(q, X).flatten()
        ranked = np.argsort(-sims)

        # Aggregate chunk scores to artifact scores (max over chunks)
        artifact_scores: Dict[int, float] = {}
        top_n = min(len(ranked), 200)
        for idx in ranked[:top_n]:
            _, artifact_id, _ = chunks[idx]
            score = float(sims[idx])
            artifact_scores[artifact_id] = max(artifact_scores.get(artifact_id, 0.0), score)

        top = sorted(artifact_scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [aid for aid, _ in top]
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Embedding retrieval (SentenceTransformers) with Cloud Run–safe fallback
# -----------------------------------------------------------------------------
_model = None
_model_load_failed = False

def _get_model() -> Optional["SentenceTransformer"]:
    """
    Loads the sentence-transformers model once per container.
    If model download/load fails (common on Cloud Run due to HF rate limits),
    we mark it failed and permanently fall back to keyword-only retrieval.
    """
    global _model, _model_load_failed

    if _model is not None:
        return _model
    if _model_load_failed:
        return None

    try:
        from sentence_transformers import SentenceTransformer  # local import

        # Cache directory: Cloud Run writable paths are /tmp
        cache_dir = os.getenv("HF_HOME", "/tmp/hf")
        os.makedirs(cache_dir, exist_ok=True)

        _model = SentenceTransformer("all-MiniLM-L6-v2", cache_folder=cache_dir)
        logger.info("Loaded SentenceTransformer model successfully.")
        return _model
    except Exception as e:
        _model_load_failed = True
        logger.exception(
            "Embedding model load failed; falling back to keyword-only retrieval. Error: %s",
            str(e),
        )
        return None


def embedding_retrieve(control_id: int, k: int = 10) -> List[int]:
    """
    Returns top-k artifact_ids by cosine similarity in embedding space.
    If the embedding model can't be loaded, returns [] (so hybrid falls back).
    """
    model = _get_model()
    if model is None:
        return []

    db = SessionLocal()
    try:
        query = control_query_text(db, control_id).strip()
        if not query:
            return []

        chunks = load_chunks(db)
        if not chunks:
            return []

        chunk_texts = [t for _, _, t in chunks]

        # Encode
        chunk_emb = model.encode(chunk_texts, normalize_embeddings=True)
        q_emb = model.encode([query], normalize_embeddings=True)

        sims = (chunk_emb @ q_emb[0]).flatten()
        ranked = np.argsort(-sims)

        # Aggregate chunk scores to artifact scores (max over chunks)
        artifact_scores: Dict[int, float] = {}
        top_n = min(len(ranked), 200)
        for idx in ranked[:top_n]:
            _, artifact_id, _ = chunks[idx]
            score = float(sims[idx])
            artifact_scores[artifact_id] = max(artifact_scores.get(artifact_id, 0.0), score)

        top = sorted(artifact_scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [aid for aid, _ in top]
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Hybrid retrieval
# -----------------------------------------------------------------------------
def hybrid_retrieve(control_id: int, k: int = 10) -> List[int]:
    """
    Simple hybrid:
    - pull lots from keyword + embedding
    - union them, keeping keyword order first, then embedding
    - take first k
    """
    kw = keyword_retrieve(control_id, k=50)
    em = embedding_retrieve(control_id, k=50)

    seen = set()
    out: List[int] = []
    for aid in kw + em:
        if aid not in seen:
            out.append(aid)
            seen.add(aid)
        if len(out) >= k:
            break

    return out
