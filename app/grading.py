import json
import math
import random
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.config import get_settings
from app.models import Answer, Grade, Question

settings = get_settings()


@dataclass
class GradeResult:
    score: float
    strengths: list[str]
    missing_points: list[str]
    feedback: str


@dataclass
class BatchGradeOutput:
    grades: list[Grade]
    model_answer_english: str | None = None
    model_answer_hebrew: str | None = None
    provider_used: str = "local"


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _contains_keyword(text: str, keyword: str) -> bool:
    keyword = keyword.lower().strip()
    if not keyword:
        return False
    return keyword in text


def local_grade_answer(question: Question, answer: Answer) -> GradeResult:
    """
    Deterministic MVP grader.

    It is cheap and offline, but it is limited: it mostly checks whether important
    rubric concepts or keywords appear in the participant answer.
    """
    expected_points: list[dict[str, Any]] = json.loads(question.expected_points_json)
    text = _normalize(answer.answer_text)

    covered: list[str] = []
    missing: list[str] = []

    for point in expected_points:
        keywords = point.get("keywords", [])
        if any(_contains_keyword(text, kw) for kw in keywords):
            covered.append(point["point"])
        else:
            missing.append(point["point"])

    coverage_ratio = len(covered) / max(len(expected_points), 1)
    concept_score = 7.0 * coverage_ratio

    word_count = len(re.findall(r"\w+", answer.answer_text, flags=re.UNICODE))
    length_score = min(2.0, math.log1p(word_count) / math.log1p(120) * 2.0)

    has_structure = any(token in answer.answer_text for token in ["1.", "2.", "-", "•", "Firstly", "First", "ראשית"])
    clarity_score = 1.0 if has_structure or word_count >= 70 else 0.6 if word_count >= 35 else 0.3

    score = round(min(10.0, concept_score + length_score + clarity_score), 1)

    if score >= 8.5:
        feedback = "Strong interview answer. It covers most core concepts and has enough depth."
    elif score >= 7.0:
        feedback = "Good answer, but it is missing a few important interview points."
    elif score >= 5.0:
        feedback = "Partial answer. The main direction is reasonable, but more technical depth is needed."
    else:
        feedback = "Weak answer for an interview. It needs clearer definitions, diagnostics, and concrete examples."

    return GradeResult(score=score, strengths=covered, missing_points=missing, feedback=feedback)


def _safe_json_loads(text: str) -> dict[str, Any]:
    """Parse JSON even if the model wraps it with markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _compact_expected_points(question: Question) -> list[str]:
    points = json.loads(question.expected_points_json)
    return [p.get("point", "") for p in points]


RETRYABLE_GEMINI_STATUS_CODES = {429, 500, 502, 503, 504}


def _gemini_model_candidates() -> list[str]:
    """
    Build an ordered fallback list.

    Recommended production setting:
        GEMINI_MODEL=gemini-2.5-flash

    Behavior:
        1. Try the configured model first.
        2. If it fails repeatedly with retryable errors, try flash.
        3. If that fails, try flash-lite.
    """
    candidates = [settings.gemini_model, "gemini-2.5-flash", "gemini-2.5-flash-lite"]
    unique: list[str] = []
    for model in candidates:
        model = (model or "").strip()
        if model and model not in unique:
            unique.append(model)
    return unique


def _gemini_generate_json_once(prompt: str, model_name: str) -> dict[str, Any]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")

    # Important: do not include the API key in exception messages/logs.
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": settings.llm_temperature,
            "maxOutputTokens": settings.llm_max_output_tokens,
            "responseMimeType": "application/json",
        },
    }
    response = requests.post(
        url,
        params={"key": settings.gemini_api_key},
        json=payload,
        timeout=120,
    )

    if response.status_code >= 400:
        body_preview = response.text[:300].replace("\n", " ")
        raise requests.HTTPError(
            f"Gemini model={model_name} status={response.status_code}: {body_preview}",
            response=response,
        )

    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _safe_json_loads(text)


def _gemini_generate_json(prompt: str) -> tuple[dict[str, Any], str]:
    """
    Call Gemini with retry + model fallback.

    For each model:
        attempt 1 immediately
        wait 2 seconds, attempt 2
        wait 4 seconds, attempt 3

    If the configured model still fails with retryable errors, fall back to
    gemini-2.5-flash and then gemini-2.5-flash-lite. If all fail, the caller
    will use the local grader.
    """
    last_error: Exception | None = None

    for model_name in _gemini_model_candidates():
        for attempt in range(3):
            try:
                data = _gemini_generate_json_once(prompt, model_name)
                if attempt > 0:
                    print(f"[grading] Gemini succeeded after retry: model={model_name} attempt={attempt + 1}")
                return data, model_name

            except requests.HTTPError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else None

                # 404 means wrong/unavailable model. Do not retry the same model.
                if status == 404:
                    print(f"[grading] Gemini model not found/unavailable, trying fallback: model={model_name}")
                    break

                # Retry only transient/quota/capacity errors.
                if status not in RETRYABLE_GEMINI_STATUS_CODES:
                    raise

                if attempt < 2:
                    wait_s = [2, 4][attempt] + random.uniform(0, 0.5)
                    print(
                        f"[grading] Gemini retryable error: model={model_name} "
                        f"status={status} attempt={attempt + 1}/3; retrying in {wait_s:.1f}s"
                    )
                    time.sleep(wait_s)
                else:
                    print(
                        f"[grading] Gemini model failed after retries: "
                        f"model={model_name} status={status}; trying next fallback model"
                    )

            except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc
                # Network errors and malformed/incomplete responses can be transient.
                if attempt < 2:
                    wait_s = [2, 4][attempt] + random.uniform(0, 0.5)
                    print(
                        f"[grading] Gemini call/parse error: model={model_name} "
                        f"attempt={attempt + 1}/3; retrying in {wait_s:.1f}s: {type(exc).__name__}"
                    )
                    time.sleep(wait_s)
                else:
                    print(
                        f"[grading] Gemini model failed after retries: "
                        f"model={model_name}; trying next fallback model: {type(exc).__name__}"
                    )

    raise RuntimeError(f"All Gemini models failed. Last error type: {type(last_error).__name__}")


def _build_batch_grading_prompt(question: Question, answers: list[Answer]) -> str:
    # Hard cap to keep cost predictable. The bot should normally have <=15 users.
    answer_payload = [
        {
            "answer_id": a.id,
            "participant": a.user.display_name,
            "answer": a.answer_text[: settings.llm_max_answer_chars],
        }
        for a in answers[: settings.llm_max_answers_per_batch]
    ]

    rubric = {
        "conceptual_correctness": 4.0,
        "depth_of_understanding": 2.0,
        "ability_to_explain_intuition": 1.5,
        "interview_structure_and_clarity": 1.0,
        "practical_examples_or_edge_cases_when_relevant": 1.0,
        "precision_without_unnecessary_theory": 0.5,
        "penalties": {
            "false_core_definition_or_reversed_concepts": "subtract 3-6 points depending on severity",
            "answer_does_not_address_question": "score should usually be 0-3",
            "buzzwords_without_explanation": "subtract up to 2 points",
            "unnecessary_equation_dump_without_understanding": "do not reward",
            "empty_or_refusal_answer": "score 0",
        },
    }

    payload = {
        "role": (
            "You are a strict but fair senior AI/Data Science interviewer at a top AI company. "
            "You evaluate real interview understanding, not school-style memorization."
        ),
        "core_goal": (
            "The participant should show that they understand the concept well enough to explain it clearly in a real interview. "
            "Prefer concise, correct, intuitive answers over long theoretical answers."
        ),
        "language_policy": [
            "Participants may answer in Hebrew, English, or mixed Hebrew-English.",
            "Do not penalize Hebrew or imperfect English grammar if the technical meaning is clear.",
            "Write the official answer twice: first English, then Hebrew.",
        ],
        "official_answer_policy": [
            "The official answer must be strong, concise, and interview-ready.",
            "Do not write a long story or textbook explanation.",
            "Write what a very strong candidate could say in a real interview and satisfy the interviewer.",
            "Include only the equations/formulas that are truly necessary for correctness.",
            "If the topic has a key equation, connect it to intuition in one sentence.",
            "Target length: about 120-220 words in English and a natural Hebrew version of similar length.",
        ],
        "equation_policy": [
            "Do not require exact theoretical equations unless the question explicitly asks for a formula, derivation, proof, or metric definition.",
            "The main goal is understanding: definition, intuition, relationship between concepts, and edge cases.",
            "Do not reward equations if the participant clearly does not understand what they mean.",
        ],
        "evaluation_style": [
            "For each participant, write one professional evaluation paragraph, not separate 'got right' and 'missing' lists.",
            "Explain clearly what is wrong or weak in the answer, especially if the answer confuses concepts.",
            "Mention the correct idea inside the feedback when needed, so the participant learns from the evaluation.",
            "Be direct but respectful, like a senior interviewer giving post-interview feedback.",
            "If the answer is mostly correct, explain what would make it stronger in a top-company interview.",
            "If the answer is empty/joke/non-answer, say that it cannot be evaluated and score it near 0.",
        ],
        "grading_rules": [
            "Grade only the submitted answer, not the participant identity.",
            "Use absolute scoring from 0 to 10, then rank by score.",
            "Do not reward long answers unless they add correct technical content.",
            "Reward clear intuition, correct distinctions, edge cases, and practical interpretation.",
            "Use the expected answer points as guidance, but accept equivalent correct explanations.",
            "Return JSON only. No markdown. No code fences.",
        ],
        "question": {
            "topic": question.topic,
            "difficulty": question.difficulty,
            "text": question.question_text,
            "current_model_answer_from_bank": question.model_answer,
            "expected_points": _compact_expected_points(question),
            "score_rubric_10_points": rubric,
        },
        "answers": answer_payload,
        "required_output_schema": {
            "model_answer_english": "Concise official interview answer in English. Strong, correct, not a long story.",
            "model_answer_hebrew": "Concise official interview answer in natural Hebrew. Strong, correct, not a long story.",
            "grades": [
                {
                    "answer_id": "integer, must match one provided answer_id",
                    "score": "number from 0 to 10, one decimal max",
                    "strengths": ["optional internal short points; can be empty"],
                    "missing_points": ["optional internal short points; can be empty"],
                    "feedback": "One professional evaluation paragraph, 3-6 sentences. Explain what is correct/incorrect, what reasoning is missing, and how to improve for a real interview. Do not use headings like Got right/Missing.",
                }
            ],
        },
    }
    return json.dumps(payload, ensure_ascii=False)

def gemini_grade_answers(question: Question, answers: list[Answer]) -> tuple[dict[int, GradeResult], str | None, str | None, str]:
    prompt = _build_batch_grading_prompt(question, answers)
    data, provider_model = _gemini_generate_json(prompt)

    results: dict[int, GradeResult] = {}
    valid_ids = {a.id for a in answers}
    for item in data.get("grades", []):
        try:
            answer_id = int(item["answer_id"])
        except Exception:
            continue
        if answer_id not in valid_ids:
            continue
        score = float(item.get("score", 0))
        score = max(0.0, min(10.0, round(score, 1)))
        strengths = item.get("strengths") or []
        missing = item.get("missing_points") or []
        feedback = str(item.get("feedback") or "No feedback returned.")
        results[answer_id] = GradeResult(
            score=score,
            strengths=[str(x) for x in strengths[:8]],
            missing_points=[str(x) for x in missing[:8]],
            feedback=feedback,
        )

    model_answer_english = data.get("model_answer_english")
    model_answer_hebrew = data.get("model_answer_hebrew")
    return results, model_answer_english, model_answer_hebrew, provider_model


def grade_answer(question: Question, answer: Answer) -> GradeResult:
    # Single-answer public function kept for compatibility.
    return local_grade_answer(question, answer)


def _save_grade(session, answer: Answer, result: GradeResult) -> Grade:
    grade = session.query(Grade).filter_by(answer_id=answer.id).first()

    if grade is None:
        grade = Grade(answer_id=answer.id, score=result.score)
        session.add(grade)

    grade.score = result.score
    grade.strengths_json = json.dumps(result.strengths, ensure_ascii=False)
    grade.missing_points_json = json.dumps(result.missing_points, ensure_ascii=False)
    grade.feedback = result.feedback
    session.commit()
    session.refresh(grade)
    return grade


def upsert_grade(session, answer: Answer, question: Question) -> Grade:
    result = local_grade_answer(question, answer)
    return _save_grade(session, answer, result)


def upsert_grades_batch(session, answers: list[Answer], question: Question) -> BatchGradeOutput:
    """
    Token-saving grading path.

    If GRADING_PROVIDER=gemini and GEMINI_API_KEY exists, all participants are graded
    in one API call. If the LLM call fails, we fall back to the deterministic local
    grader so /grade still works.
    """
    if not answers:
        return BatchGradeOutput(grades=[], provider_used="none")

    results: dict[int, GradeResult] = {}
    model_answer_english: str | None = None
    model_answer_hebrew: str | None = None
    provider_used = "local"

    if settings.grading_provider == "gemini" and settings.gemini_api_key:
        try:
            results, model_answer_english, model_answer_hebrew, provider_model = gemini_grade_answers(question, answers)
            provider_used = f"gemini:{provider_model}"
        except Exception as exc:
            # Do not print the API key or raw request URL.
            print(f"[grading] Gemini grading failed after retries/fallbacks; using local grader. Error type: {type(exc).__name__}; message: {str(exc)[:300]}")

    grades: list[Grade] = []
    for answer in answers:
        result = results.get(answer.id) or local_grade_answer(question, answer)
        grades.append(_save_grade(session, answer, result))

    return BatchGradeOutput(
        grades=grades,
        model_answer_english=model_answer_english,
        model_answer_hebrew=model_answer_hebrew,
        provider_used=provider_used,
    )
