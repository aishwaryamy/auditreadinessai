from datetime import timezone
from google.cloud import bigquery

from .db import SessionLocal
from .models import Control, ControlScore, Gap

PROJECT_ID = "auditreadinessai"
BQ_DATASET = "auditreadiness"
BQ_TABLE_SCORES = "control_scores"
BQ_TABLE_GAPS = "gaps"

def get_max_id(client: bigquery.Client, table_id: str, id_field: str) -> int:
    query = f"SELECT MAX({id_field}) AS max_id FROM `{table_id}`"
    result = client.query(query).result()
    for row in result:
        return int(row["max_id"] or 0)
    return 0

def to_utc_iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def export_scores(client: bigquery.Client):
    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE_SCORES}"
    max_score_id = get_max_id(client, table_id, "score_id")

    db = SessionLocal()
    try:
        scores = db.query(ControlScore).filter(ControlScore.id > max_score_id).all()
        rows = []

        for s in scores:
            c = db.query(Control).filter(Control.id == s.control_id).first()
            if not c:
                continue

            rows.append(
                {
                    "score_id": s.id,
                    "control_id": c.id,
                    "control_code": c.code,
                    "control_title": c.title,
                    "category": c.category,
                    "coverage_pct": float(s.coverage_pct),
                    "freshness_score": float(s.freshness_score),
                    "source_credibility": float(s.source_credibility),
                    "readiness_score": float(s.readiness_score),
                    "computed_at": to_utc_iso(s.computed_at),
                }
            )

        if not rows:
            print(f"No new ControlScore rows to export. (max_score_id={max_score_id})")
            return

        errors = client.insert_rows_json(table_id, rows)
        print("Errors:", errors if errors else "None")
        print(f"Exported {len(rows)} NEW rows to {table_id}")
    finally:
        db.close()

def export_gaps(client: bigquery.Client):
    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE_GAPS}"
    max_gap_id = get_max_id(client, table_id, "gap_id")

    db = SessionLocal()
    try:
        gaps = db.query(Gap).filter(Gap.id > max_gap_id).all()
        rows = []

        for g in gaps:
            c = db.query(Control).filter(Control.id == g.control_id).first()
            if not c:
                continue

            rows.append(
                {
                    "gap_id": g.id,
                    "control_id": c.id,
                    "control_code": c.code,
                    "severity": g.severity,
                    "reason": g.reason,
                    "created_at": to_utc_iso(g.created_at),
                    "resolved_at": to_utc_iso(g.resolved_at),
                }
            )

        if not rows:
            print(f"No new Gap rows to export. (max_gap_id={max_gap_id})")
            return

        errors = client.insert_rows_json(table_id, rows)
        print("Errors:", errors if errors else "None")
        print(f"Exported {len(rows)} NEW rows to {table_id}")
    finally:
        db.close()

def main():
    client = bigquery.Client(project=PROJECT_ID)
    export_scores(client)
    export_gaps(client)


if __name__ == "__main__":
    main()
