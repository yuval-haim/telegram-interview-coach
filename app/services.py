from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo
from html import escape

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.grading import BatchGradeOutput, upsert_grades_batch
from app.models import Answer, Chat, DailyQuestion, Grade, Question, User

settings = get_settings()


def today_str() -> str:
    return datetime.now(ZoneInfo(settings.timezone)).date().isoformat()


def ensure_chat(session: Session, telegram_chat_id: int, title: str | None) -> Chat:
    chat = session.query(Chat).filter_by(telegram_chat_id=telegram_chat_id).first()
    if chat is None:
        chat = Chat(telegram_chat_id=telegram_chat_id, title=title, is_active=True)
        session.add(chat)
    else:
        chat.title = title or chat.title
        chat.is_active = True
    session.commit()
    session.refresh(chat)
    return chat


def ensure_user(session: Session, tg_user) -> User:
    display_name = " ".join(part for part in [tg_user.first_name, tg_user.last_name] if part).strip()
    if not display_name:
        display_name = tg_user.username or str(tg_user.id)

    user = session.query(User).filter_by(telegram_user_id=tg_user.id).first()
    if user is None:
        user = User(telegram_user_id=tg_user.id, display_name=display_name, username=tg_user.username)
        session.add(user)
    else:
        user.display_name = display_name
        user.username = tg_user.username
    session.commit()
    session.refresh(user)
    return user


def pick_next_question(session: Session, chat_id: int) -> Question:
    """Pick an active question with simple least-used ordering."""
    used_counts = (
        session.query(DailyQuestion.question_id, func.count(DailyQuestion.id).label("cnt"))
        .filter(DailyQuestion.chat_id == chat_id)
        .group_by(DailyQuestion.question_id)
        .subquery()
    )

    question = (
        session.query(Question)
        .outerjoin(used_counts, Question.id == used_counts.c.question_id)
        .filter(Question.active.is_(True))
        .order_by(func.coalesce(used_counts.c.cnt, 0).asc(), Question.id.asc())
        .first()
    )

    if question is None:
        raise RuntimeError("No active questions found. Seed or create questions first.")
    return question


def ensure_daily_question(session: Session, chat: Chat, local_date: str | None = None) -> DailyQuestion:
    local_date = local_date or today_str()
    dq = session.query(DailyQuestion).filter_by(chat_id=chat.id, date=local_date).first()
    if dq is not None:
        return dq

    question = pick_next_question(session, chat.id)
    dq = DailyQuestion(chat_id=chat.id, question_id=question.id, date=local_date, status="active")
    session.add(dq)
    session.commit()
    session.refresh(dq)
    return dq


def get_today_question_for_telegram_chat(session: Session, telegram_chat_id: int) -> DailyQuestion | None:
    chat = session.query(Chat).filter_by(telegram_chat_id=telegram_chat_id, is_active=True).first()
    if chat is None:
        return None
    return session.query(DailyQuestion).filter_by(chat_id=chat.id, date=today_str()).first()


def get_daily_question_by_message(session: Session, telegram_chat_id: int, message_id: int) -> DailyQuestion | None:
    chat = session.query(Chat).filter_by(telegram_chat_id=telegram_chat_id, is_active=True).first()
    if chat is None:
        return None
    return session.query(DailyQuestion).filter_by(chat_id=chat.id, message_id=message_id).first()


def upsert_answer(session: Session, dq: DailyQuestion, user: User, answer_text: str, telegram_message_id: int | None) -> Answer:
    answer = session.query(Answer).filter_by(daily_question_id=dq.id, user_id=user.id).first()
    if answer is None:
        answer = Answer(
            daily_question_id=dq.id,
            user_id=user.id,
            answer_text=answer_text,
            telegram_message_id=telegram_message_id,
        )
        session.add(answer)
    else:
        answer.answer_text = answer_text
        answer.telegram_message_id = telegram_message_id
    session.commit()
    session.refresh(answer)
    return answer


def format_question_message(dq: DailyQuestion) -> str:
    q = dq.question
    return (
        f"🧠 <b>Daily AI/Data Science Interview Question</b>\n"
        f"<b>Date:</b> {dq.date}\n"
        f"<b>Topic:</b> {escape(q.topic)}\n"
        f"<b>Difficulty:</b> {escape(q.difficulty)}\n\n"
        f"{escape(q.question_text)}\n\n"
        f"Reply to this message with your answer in Hebrew or English. "
        f"You can update your answer by replying again before grading time."
    )


def grade_daily_question(session: Session, dq: DailyQuestion) -> BatchGradeOutput:
    answers = session.query(Answer).filter_by(daily_question_id=dq.id).all()
    batch = upsert_grades_batch(session, answers, dq.question)

    batch.grades.sort(key=lambda g: g.score, reverse=True)
    for idx, grade in enumerate(batch.grades, start=1):
        grade.rank = idx
    dq.status = "graded"
    session.commit()
    return batch


def format_grading_report(dq: DailyQuestion, batch: BatchGradeOutput | list[Grade]) -> str:
    # Backward compatible: older callers may pass a plain grades list.
    if isinstance(batch, list):
        grades = batch
        model_answer_english = dq.question.model_answer
        model_answer_hebrew = None
        provider_used = "unknown"
    else:
        grades = batch.grades
        model_answer_english = batch.model_answer_english or dq.question.model_answer
        model_answer_hebrew = batch.model_answer_hebrew
        provider_used = batch.provider_used

    q = dq.question
    if not grades:
        lines = [
            f"📊 <b>Daily Results — {dq.date}</b>",
            "",
            "No answers were submitted today.",
            "",
            "✅ <b>Official interview answer — English</b>",
            escape(model_answer_english),
        ]
        if model_answer_hebrew:
            lines.extend(["", "✅ <b>תשובה רשמית לראיון — עברית</b>", escape(model_answer_hebrew)])
        return "\n".join(lines)

    lines = [
        f"📊 <b>Daily Results — {dq.date}</b>",
        f"<b>Topic:</b> {escape(q.topic)}",
        f"<b>Judge:</b> {escape(provider_used)}",
        "",
        "✅ <b>Official interview answer — English</b>",
        escape(model_answer_english),
    ]

    if model_answer_hebrew:
        lines.extend(["", "✅ <b>תשובה רשמית לראיון — עברית</b>", escape(model_answer_hebrew)])

    lines.extend(["", "🏆 <b>Participant evaluation</b>"])

    for grade in grades:
        answer = grade.answer
        lines.extend(
            [
                f"\n<b>{grade.rank}. {escape(answer.user.display_name)} — {grade.score:.1f}/10</b>",
                f"<b>Evaluation:</b> {escape(grade.feedback)}",
            ]
        )

    return "\n".join(lines)

def leaderboard_text(session: Session, days: int = 7) -> str:
    # MVP: all-time leaderboard. We can add date filtering later.
    rows = (
        session.query(User.display_name, func.count(Grade.id), func.avg(Grade.score), func.sum(Grade.score))
        .join(Answer, Answer.user_id == User.id)
        .join(Grade, Grade.answer_id == Answer.id)
        .group_by(User.id)
        .order_by(func.sum(Grade.score).desc())
        .all()
    )

    if not rows:
        return "No graded answers yet."

    lines = ["🏆 <b>Leaderboard</b>", ""]
    for idx, (name, count, avg_score, total_score) in enumerate(rows, start=1):
        lines.append(f"{idx}. <b>{escape(name)}</b> — total {total_score:.1f}, avg {avg_score:.1f}, answers {count}")
    return "\n".join(lines)
