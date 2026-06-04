# Architecture

## Main Components

```text
app/main.py
  Starts the FastAPI service, Telegram polling bot, database initialization, question seeding, and scheduler.

app/bot_handlers.py
  Telegram command handlers and answer collection logic.

app/services.py
  Business logic: chat activation, daily question selection, answer upsert, grading report formatting, leaderboard.

app/grading.py
  Local rubric grader and optional Gemini batch grading.

app/scheduler.py
  Daily question and daily grading jobs.

app/api.py
  FastAPI health and status endpoints.

app/models.py
  SQLAlchemy models.

question_bank/seed_questions.json
  Curated interview question bank.
```

## Data Model

```text
Chat
  Telegram group activation state.

User
  Telegram participant identity.

Question
  Seeded interview question with rubric metadata.

DailyQuestion
  One question assigned to one group on one date.

Answer
  Latest participant answer for a daily question.

Grade
  Score, rank, strengths, missing points, and feedback for one answer.
```

## Grading Flow

```text
/grade
  → fetch today's DailyQuestion
  → fetch submitted answers
  → grade with local rubric or Gemini batch judge
  → assign ranks
  → format official answer + feedback report
  → post report to Telegram group
```
