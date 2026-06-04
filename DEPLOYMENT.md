# Deployment Guide

This bot can run locally with polling, or on a small always-on service.

## Recommended free/near-free MVP setup

For a zero-cost hobby MVP, use:

- **Koyeb Free Instance** for the Python app
- **SQLite** only for temporary testing, or **Supabase/Neon Postgres** for persistent data
- **Gemini Flash-Lite** for low-cost LLM grading, or `GRADING_PROVIDER=local` for free grading

Important: local filesystem storage in many cloud services is ephemeral. For serious use, use Postgres.

## Deployment environment variables

Set these variables in your hosting provider:

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=sqlite:///./interview_bot.db
TIMEZONE=Asia/Jerusalem
DAILY_QUESTION_HOUR=9
DAILY_QUESTION_MINUTE=0
DAILY_GRADE_HOUR=21
DAILY_GRADE_MINUTE=0
GRADING_PROVIDER=local
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash-lite
```

For persistent Postgres, replace `DATABASE_URL` with something like:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/postgres
```

## Koyeb deployment steps

1. Push this project to a GitHub repository.
2. Create a Koyeb account.
3. Create a new Web Service from your GitHub repository.
4. Koyeb should detect the Dockerfile. If asked, choose Dockerfile deployment.
5. Add the environment variables above.
6. Deploy.
7. Open the public service URL and check `/health`.
8. In Telegram, run `/today` and `/grade` in your group.

## Railway / Render note

Railway works well but is not fully free for an always-on app. Render Free Web Services can spin down after inactivity, which is not ideal for a polling bot and scheduled jobs unless you redesign to use webhooks plus an external cron wake-up.

## Production upgrade path

For real production:

1. Use Postgres instead of SQLite.
2. Add database migrations with Alembic.
3. Switch from polling to Telegram webhooks.
4. Add admin-only permissions for `/grade`, `/today`, and `/activate`.
5. Add structured logs and error alerts.
6. Track LLM token usage and grading failures.
