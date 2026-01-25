# auditreadinessai
## Retrieval Evaluation (Applied LLM/DS)

This project includes an offline evaluation harness for evidence retrieval quality across SOC 2 controls.

### Methods
- **Keyword baseline**: TF-IDF cosine similarity over evidence chunks
- **Embedding retrieval**: SentenceTransformers (all-MiniLM-L6-v2)
- **Hybrid**: union of keyword + embedding results

### Metrics
- **Precision@5**: fraction of top-5 retrieved artifacts that are relevant
- **Recall@10**: fraction of all relevant artifacts retrieved in top-10
- **MRR** (Mean Reciprocal Rank): how early the first relevant artifact appears

### Current results (initial labeled set)
