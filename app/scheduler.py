from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from app.bot_handlers import post_daily_question, send_long_message
from app.config import get_settings
from app.db import SessionLocal
from app.models import Chat
from app.services import format_grading_report, get_today_question_for_telegram_chat, grade_daily_question

settings = get_settings()


async def send_daily_questions(bot: Bot) -> None:
    with SessionLocal() as session:
        chats = session.query(Chat).filter_by(is_active=True).all()
        chat_refs = [(chat.telegram_chat_id, chat.title) for chat in chats]

    for telegram_chat_id, title in chat_refs:
        await post_daily_question(bot, telegram_chat_id, title)


async def grade_daily_questions(bot: Bot) -> None:
    with SessionLocal() as session:
        chats = session.query(Chat).filter_by(is_active=True).all()
        chat_ids = [chat.telegram_chat_id for chat in chats]

    for telegram_chat_id in chat_ids:
        with SessionLocal() as session:
            dq = get_today_question_for_telegram_chat(session, telegram_chat_id)
            if dq is None:
                continue
            batch = grade_daily_question(session, dq)
            report = format_grading_report(dq, batch)
        await send_long_message(bot, telegram_chat_id, report)


def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        send_daily_questions,
        CronTrigger(hour=settings.daily_question_hour, minute=settings.daily_question_minute, timezone=settings.timezone),
        args=[bot],
        id="send_daily_questions",
        replace_existing=True,
    )
    scheduler.add_job(
        grade_daily_questions,
        CronTrigger(hour=settings.daily_grade_hour, minute=settings.daily_grade_minute, timezone=settings.timezone),
        args=[bot],
        id="grade_daily_questions",
        replace_existing=True,
    )
    return scheduler
