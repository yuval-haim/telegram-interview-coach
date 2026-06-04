from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_user_id = Column(Integer, unique=True, index=True, nullable=False)
    display_name = Column(String(255), nullable=False)
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True)
    telegram_chat_id = Column(Integer, unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(120), unique=True, index=True, nullable=False)
    topic = Column(String(120), nullable=False)
    difficulty = Column(String(50), nullable=False)
    question_text = Column(Text, nullable=False)
    model_answer = Column(Text, nullable=False)
    expected_points_json = Column(Text, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    extras_json = Column(Text, nullable=True)


class DailyQuestion(Base):
    __tablename__ = "daily_questions"
    __table_args__ = (UniqueConstraint("chat_id", "date", name="uq_daily_question_chat_date"),)

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD in local timezone
    message_id = Column(Integer, nullable=True)
    status = Column(String(30), default="active", nullable=False)  # active | graded
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    chat = relationship("Chat")
    question = relationship("Question")


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("daily_question_id", "user_id", name="uq_answer_daily_user"),)

    id = Column(Integer, primary_key=True)
    daily_question_id = Column(Integer, ForeignKey("daily_questions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    answer_text = Column(Text, nullable=False)
    telegram_message_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    daily_question = relationship("DailyQuestion")
    user = relationship("User")


class Grade(Base):
    __tablename__ = "grades"

    id = Column(Integer, primary_key=True)
    answer_id = Column(Integer, ForeignKey("answers.id"), unique=True, nullable=False)
    score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=True)
    strengths_json = Column(Text, nullable=False)
    missing_points_json = Column(Text, nullable=False)
    feedback = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    answer = relationship("Answer")
