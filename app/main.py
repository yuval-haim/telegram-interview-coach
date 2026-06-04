from __future__ import annotations

import asyncio
import logging
import os

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.api import app as fastapi_app
from app.bot_handlers import router
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.scheduler import build_scheduler
from app.seed import seed_questions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


async def run_api() -> None:
    config = uvicorn.Config(
        fastapi_app,
        host=settings.api_host,
        port=int(os.getenv("PORT", str(settings.api_port))),
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = build_scheduler(bot)
    scheduler.start()

    logger.info("Bot polling started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def main() -> None:
    init_db()
    with SessionLocal() as session:
        created = seed_questions(session)
        logger.info("Seeded %s new questions", created)

    await asyncio.gather(run_api(), run_bot())


if __name__ == "__main__":
    asyncio.run(main())
