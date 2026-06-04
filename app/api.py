from fastapi import FastAPI
from sqlalchemy import func

from app.db import SessionLocal
from app.models import Answer, Chat, DailyQuestion, Grade, Question, User
from app.services import today_str

app = FastAPI(title="AI Interview Telegram Bot MVP")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict:
    with SessionLocal() as session:
        return {
            "today": today_str(),
            "active_chats": session.query(Chat).filter_by(is_active=True).count(),
            "users": session.query(User).count(),
            "questions": session.query(Question).filter_by(active=True).count(),
            "daily_questions": session.query(DailyQuestion).count(),
            "answers": session.query(Answer).count(),
            "grades": session.query(Grade).count(),
            "avg_score": session.query(func.avg(Grade.score)).scalar(),
        }
