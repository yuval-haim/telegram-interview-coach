# GitHub Repository Guide

This guide shows how to turn the existing deployed bot into a clean public GitHub repository without leaking secrets or private Telegram data.

## 1. Final privacy check

Before committing, make sure these files are not present:

```bash
find . -name ".env" -o -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" -o -name "*.backup*"
```

If any real database or secret file appears, remove it from the repo folder before `git add`.

## 2. Initialize Git

```bash
git init
git branch -M main
```

## 3. Make logical commits

Use several real commits that represent how the project was built.

```bash
git add README.md LICENSE .gitignore .dockerignore requirements.txt Dockerfile docker-compose.yml Procfile .env.example
git commit -m "Initialize Telegram interview bot repository"


git add app/config.py app/db.py app/models.py app/seed.py question_bank/seed_questions.json data/README.md data/.gitkeep
git commit -m "Add persistence layer and interview question bank"


git add app/bot_handlers.py app/services.py app/scheduler.py app/main.py
git commit -m "Add Telegram bot workflows and daily scheduler"


git add app/grading.py LLM_GRADING.md
git commit -m "Add rubric and optional LLM grading"


git add app/api.py DEPLOYMENT.md
git commit -m "Add FastAPI health endpoints and deployment docs"


git add assets/demo docs/GIT_REPO_GUIDE.md README.md
git commit -m "Add anonymized demo screenshots and GitHub documentation"
```

## 4. Create the GitHub repo

Create an empty repository on GitHub, for example:

```text
telegram-interview-coach
```

Recommended short description:

```text
Telegram bot for daily AI/Data Science interview practice with scheduled questions, answer collection, LLM grading, and leaderboards.
```

## 5. Push

```bash
git remote add origin https://github.com/YOUR_USERNAME/telegram-interview-coach.git
git push -u origin main
```

If the remote already exists:

```bash
git remote set-url origin https://github.com/YOUR_USERNAME/telegram-interview-coach.git
git push -u origin main
```

## 6. Verify GitHub did not receive secrets

After pushing, check the GitHub file list and confirm that these are absent:

- `.env`
- `interview_bot.db`
- `data/*.db`
- Telegram IDs
- API keys
- raw unblurred screenshots

## 7. Optional: add topics

Good GitHub topics:

```text
telegram-bot
ai-engineering
interview-prep
data-science
fastapi
aiogram
llm
scheduler
docker
```
