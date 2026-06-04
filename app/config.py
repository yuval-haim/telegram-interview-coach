from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    database_url: str = "sqlite:///./interview_bot.db"
    timezone: str = "Asia/Jerusalem"

    daily_question_hour: int = 9
    daily_question_minute: int = 0
    daily_grade_hour: int = 21
    daily_grade_minute: int = 0

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Grading mode:
    # - local: deterministic keyword/rubric grader, no LLM cost
    # - gemini: one low-cost Gemini API call per daily grading batch
    grading_provider: Literal["local", "gemini"] = "local"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    llm_max_output_tokens: int = 9000
    llm_temperature: float = 0.0
    llm_max_answer_chars: int = 2500
    llm_max_answers_per_batch: int = 15

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
