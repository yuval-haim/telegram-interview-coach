# LLM Grading Guide

The project supports two grading modes.

## 1. Local grading

```env
GRADING_PROVIDER=local
```

This is free and deterministic. It checks expected answer points and keywords. It is good for testing, but it is not a real interview-quality judge and may under-grade Hebrew answers.

## 2. Gemini LLM grading

```env
GRADING_PROVIDER=gemini
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-2.5-flash-lite
```

This mode grades all participants in **one API call per daily question**, which saves tokens compared with grading each participant separately.

The prompt includes:

- the question
- model answer
- expected points
- scoring rubric
- all participant answers

The LLM must return JSON only:

```json
{
  "grades": [
    {
      "answer_id": 1,
      "score": 8.4,
      "strengths": ["..."],
      "missing_points": ["..."],
      "feedback": "..."
    }
  ]
}
```

If the Gemini request fails, the code automatically falls back to local grading so `/grade` still works.

## Token-saving strategy

- One grading call per group per day.
- Use `gemini-2.5-flash-lite` by default.
- Keep participant answers capped inside the grading prompt.
- Keep output concise.
- Use the local grader during development.
- Later, add model routing: local grader for obvious answers, LLM only for serious final grading.
