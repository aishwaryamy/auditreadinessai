import os

def read_text_from_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()

    # For MVP: only reliably index text-based files
    if ext in [".txt", ".md", ".csv", ".json", ".log"]:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    # PDFs/images: skip for now (later we’ll add PDF parsing/OCR)
    return ""


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150):
    text = " ".join(text.split())  # normalize whitespace
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        start = end - overlap
        if start < 0:
            start = 0
        if end == len(text):
            break
    return chunks
