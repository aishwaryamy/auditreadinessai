import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

from .db import SessionLocal
from .models import Control, ChecklistItem, Artifact, ArtifactChunk


def control_query_text(db, control_id: int) -> str:
    c = db.query(Control).filter(Control.id == control_id).first()
    items = db.query(ChecklistItem).filter(ChecklistItem.control_id == control_id).all()
    parts = [c.code, c.title, c.description] + [it.text for it in items]
    return " ".join([p for p in parts if p])


def load_chunks(db):
    rows = db.query(ArtifactChunk).all()
    # return: chunk_id, artifact_id, text
    return [(r.id, r.artifact_id, r.text) for r in rows]


def keyword_retrieve(control_id: int, k: int = 10):
    db = SessionLocal()
    try:
        query = control_query_text(db, control_id)
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
        artifact_scores = {}
        for idx in ranked[: min(len(ranked), 200)]:
            _, artifact_id, _ = chunks[idx]
            score = float(sims[idx])
            artifact_scores[artifact_id] = max(artifact_scores.get(artifact_id, 0.0), score)

        top = sorted(artifact_scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [aid for aid, _ in top]
    finally:
        db.close()


_model = None
def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embedding_retrieve(control_id: int, k: int = 10):
    db = SessionLocal()
    try:
        query = control_query_text(db, control_id)
        chunks = load_chunks(db)
        if not chunks:
            return []

        model = _get_model()
        chunk_texts = [t for _, _, t in chunks]

        chunk_emb = model.encode(chunk_texts, normalize_embeddings=True)
        q_emb = model.encode([query], normalize_embeddings=True)

        sims = (chunk_emb @ q_emb[0]).flatten()
        ranked = np.argsort(-sims)

        artifact_scores = {}
        for idx in ranked[: min(len(ranked), 200)]:
            _, artifact_id, _ = chunks[idx]
            score = float(sims[idx])
            artifact_scores[artifact_id] = max(artifact_scores.get(artifact_id, 0.0), score)

        top = sorted(artifact_scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [aid for aid, _ in top]
    finally:
        db.close()


def hybrid_retrieve(control_id: int, k: int = 10):
    # simple hybrid: union then keep keyword order + fill with embedding
    kw = keyword_retrieve(control_id, k=50)
    em = embedding_retrieve(control_id, k=50)
    seen = set()
    out = []
    for aid in kw + em:
        if aid not in seen:
            out.append(aid)
            seen.add(aid)
        if len(out) >= k:
            break
    return out
