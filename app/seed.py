import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Question


QUESTION_BANK_PATH = Path(__file__).resolve().parent.parent / "question_bank" / "seed_questions.json"


def seed_questions(session: Session) -> int:
    """Load seed questions into the DB if they do not already exist."""
    data = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
    created = 0

    for item in data:
        exists = session.query(Question).filter_by(external_id=item["external_id"]).first()
        if exists:
            continue

        q = Question(
            external_id=item["external_id"],
            topic=item["topic"],
            difficulty=item["difficulty"],
            question_text=item["question_text"],
            model_answer=item["model_answer"],
            expected_points_json=json.dumps(item["expected_points"], ensure_ascii=False),
            active=True,
        )
        session.add(q)
        created += 1

    session.commit()
    return created
