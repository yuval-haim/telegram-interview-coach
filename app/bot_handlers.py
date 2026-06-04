from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import ForceReply, Message

from app.db import SessionLocal
from app.models import Chat, DailyQuestion
from app.services import (
    ensure_chat,
    ensure_daily_question,
    ensure_user,
    format_grading_report,
    format_question_message,
    get_daily_question_by_message,
    get_today_question_for_telegram_chat,
    grade_daily_question,
    leaderboard_text,
    upsert_answer,
)
import os

router = Router()

GROUP_TYPES = {"group", "supergroup"}

@router.message(Command("whoami"))
async def whoami_command(message: Message) -> None:
    user = message.from_user
    if user is None:
        await message.answer("Could not detect user.")
        return

    await message.answer(
        f"Your Telegram user ID is:\n`{user.id}`",
        parse_mode="Markdown"
    )

async def send_long_message(bot: Bot, chat_id: int, text: str) -> None:
    # Telegram has a 4096-char limit. Keep chunks safely below it.
    max_len = 3800
    for start in range(0, len(text), max_len):
        await bot.send_message(chat_id=chat_id, text=text[start : start + max_len])


async def post_daily_question(bot: Bot, telegram_chat_id: int, chat_title: str | None = None) -> DailyQuestion:
    with SessionLocal() as session:
        chat = ensure_chat(session, telegram_chat_id, chat_title)
        dq = ensure_daily_question(session, chat)
        text = format_question_message(dq)

        sent = await bot.send_message(
            chat_id=telegram_chat_id,
            text=text,
            reply_markup=ForceReply(
                force_reply=True,
                input_field_placeholder="Write your answer in Hebrew or English...",
                selective=False,
            ),
        )
        dq.message_id = sent.message_id
        dq.status = "active"
        session.commit()
        session.refresh(dq)
        return dq


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Hi! I am your AI/Data Science interview practice bot.\n\n"
        "Add me to a Telegram group and run /activate there.\n"
        "Then use /today to post the first question."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Commands:\n"
        "/activate — activate this group for daily questions\n"
        "/today — post today’s question now\n"
        "/answer your text — submit/update your answer manually\n"
        "/grade — grade today’s answers now\n"
        "/leaderboard — show ranking\n\n"
        "Best UX: reply directly to the daily question message."
    )


@router.message(Command("activate"))
async def cmd_activate(message: Message) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer("Please run /activate inside the study group.")
        return

    with SessionLocal() as session:
        chat = ensure_chat(session, message.chat.id, message.chat.title)

    await message.answer(
        f"✅ Activated this group: {chat.title or chat.telegram_chat_id}\n"
        "Use /today to post the first interview question."
    )


@router.message(Command("today"))
async def cmd_today(message: Message, bot: Bot) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer("/today should be used inside the study group.")
        return

    await post_daily_question(bot, message.chat.id, message.chat.title)


@router.message(Command("answer"))
async def cmd_answer(message: Message) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer("Please answer inside the study group, or reply directly to the daily question.")
        return

    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Usage: /answer your full answer here")
        return

    with SessionLocal() as session:
        dq = get_today_question_for_telegram_chat(session, message.chat.id)
        if dq is None:
            await message.answer("No active question for today. Use /today first.")
            return

        user = ensure_user(session, message.from_user)
        upsert_answer(session, dq, user, parts[1].strip(), message.message_id)

    await message.answer("✅ Answer saved. If you submit again before grading, I will keep the latest version.")


@router.message(Command("grade"))
async def cmd_grade(message: Message, bot: Bot) -> None:
    if message.chat.type not in GROUP_TYPES:
        await message.answer("/grade should be used inside the study group.")
        return
    
    if not is_admin_user(message):
        await message.answer("⛔ Only the group admin can run /grade.")
        return

    with SessionLocal() as session:
        dq = get_today_question_for_telegram_chat(session, message.chat.id)
        if dq is None:
            await message.answer("No question found for today. Use /today first.")
            return
        batch = grade_daily_question(session, dq)
        report = format_grading_report(dq, batch)

    await send_long_message(bot, message.chat.id, report)


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message) -> None:
    with SessionLocal() as session:
        text = leaderboard_text(session)
    await message.answer(text)


@router.message(F.reply_to_message & F.text)
async def collect_reply_answer(message: Message) -> None:
    if message.chat.type not in GROUP_TYPES:
        return
    if not message.text or message.text.startswith("/"):
        return

    replied_message_id = message.reply_to_message.message_id

    with SessionLocal() as session:
        dq = get_daily_question_by_message(session, message.chat.id, replied_message_id)
        if dq is None:
            return

        user = ensure_user(session, message.from_user)
        upsert_answer(session, dq, user, message.text.strip(), message.message_id)

    await message.reply("✅ Answer saved/updated.")

def is_admin_user(message: Message) -> bool:
    raw_ids = os.getenv("ADMIN_TELEGRAM_USER_IDS", "").strip()

    # If not configured, keep commands open for local development.
    if not raw_ids:
        return True

    allowed_ids = {
        int(x.strip())
        for x in raw_ids.split(",")
        if x.strip().isdigit()
    }

    user_id = message.from_user.id if message.from_user else None
    return user_id in allowed_ids
