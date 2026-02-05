import pandas as pd
from collections import defaultdict

from api.retrieval import keyword_retrieve, embedding_retrieve, hybrid_retrieve


def precision_at_k(pred, rel_set, k):
    top = pred[:k]
    if not top:
        return 0.0
    hits = sum(1 for a in top if a in rel_set)
    return hits / k


def recall_at_k(pred, rel_set, k):
    if not rel_set:
        return 0.0
    top = pred[:k]
    hits = sum(1 for a in top if a in rel_set)
    return hits / len(rel_set)


def mrr(pred, rel_set):
    for i, a in enumerate(pred, start=1):
        if a in rel_set:
            return 1.0 / i
    return 0.0


def run(method_name, method_fn, labels, k_p=5, k_r=10):
    control_to_rel = defaultdict(set)
    for _, row in labels.iterrows():
        if int(row["relevance"]) >= 1:
            control_to_rel[int(row["control_id"])].add(int(row["artifact_id"]))

    p_scores, r_scores, mrr_scores = [], [], []

    for control_id, rel_set in control_to_rel.items():
        pred = method_fn(control_id, k=50)
        p_scores.append(precision_at_k(pred, rel_set, k_p))
        r_scores.append(recall_at_k(pred, rel_set, k_r))
        mrr_scores.append(mrr(pred, rel_set))

    print(f"\n== {method_name} ==")
    print(f"Precision@{k_p}: {sum(p_scores)/len(p_scores):.3f}")
    print(f"Recall@{k_r}:    {sum(r_scores)/len(r_scores):.3f}")
    print(f"MRR:             {sum(mrr_scores)/len(mrr_scores):.3f}")


def main():
    labels = pd.read_csv("eval/retrieval_labels.csv", comment="#")
    labels = labels.dropna(subset=["control_id", "artifact_id", "relevance"])

    if labels.empty:
        print("No labels yet. Add rows to eval/retrieval_labels.csv")
        return

    run("Keyword (TF-IDF)", keyword_retrieve, labels)
    run("Embedding (MiniLM)", embedding_retrieve, labels)
    run("Hybrid (union)", hybrid_retrieve, labels)


if __name__ == "__main__":
    main()
