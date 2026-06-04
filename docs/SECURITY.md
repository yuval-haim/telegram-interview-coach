# Security and Privacy Notes

This project interacts with Telegram groups and can store user-generated answers. Treat the database as private.

## Never commit

- `.env`
- Telegram bot token
- Gemini API key
- SQLite database files
- Telegram chat IDs
- Telegram user IDs
- raw screenshots with real names

## Recommended production settings

Use `ADMIN_TELEGRAM_USER_IDS` to restrict admin commands:

```env
ADMIN_TELEGRAM_USER_IDS=123456789,987654321
```

Use a persistent database for production:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/postgres
```

Keep FastAPI status endpoints bound to localhost unless you intentionally expose them:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```
