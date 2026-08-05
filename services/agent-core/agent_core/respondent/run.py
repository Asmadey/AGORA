"""
Прогон анкеты синтетическими респондентами — задача #18.

Каждая персона проходит анкету в структурной изоляции: её срез состоит из
собственной DNA, материала видео (Content Pack, #17) и анкеты. Больше ничего.

─── Изоляция структурная, а не по договорённости ─────────────────────────────
«Изоляция» здесь означает не «мы не кладём чужое в промпт», а «положить чужое
некуда». Разница видна на дефекте, который эта задача обязана исключить.

Опасна не склейка двух промптов — её замечают сразу. Опасен общий изменяемый
объект: список messages, словарь контекста, шаблон с подстановкой на месте,
переиспользуемый между вызовами. Он копит данные предыдущей персоны и
проявляется не на второй персоне, а на двадцатой, и только на второй репликации.
Тест на двух персонах такого не увидит.

Поэтому здесь: контекст собирается функцией из аргументов и не хранится;
шаблоны читаются один раз и подставляются в новую строку; клиент получает
system и user отдельными строками и не ведёт истории. Утечке негде поместиться,
и это утверждение проверяется тестом по ВСЕМ отправленным промптам.

─── Почему пачки по пять ──────────────────────────────────────────────────────
Размер партии из PRD §8 (MAP через Send, пачки по 5). Он про темп обращений к
провайдеру, а не про изоляцию: персоны внутри пачки по-прежнему не видят друг
друга. Пачка нужна, чтобы отказ на одном ответе не отменял остальные и чтобы
прогресс (#12) обновлялся не после пятисот ответов, а после каждых пяти.

─── Отказ модели не отменяет прогон ───────────────────────────────────────────
Ответ одной персоны — независимое наблюдение. Ронять весь прогон из-за одного
таймаута значит терять четыреста девяносто девять оплаченных ответов ради
пятисотого. Отказы считаются и попадают в артефакт: отчёт обязан знать, на
скольких ответах он построен.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .diversity import diversity_report

#: Размер пачки (PRD §8). Проверяется тестом задачи: число здесь — контракт.
BATCH_SIZE = 5

#: Таймаут одного ответа. Персона пишет несколько абзацев и JSON — дольше, чем
#: обогащение портрета, но заметно короче разбора картинки.
REQUEST_TIMEOUT_SEC = 120


def _find_prompt(name: str) -> Path:
    """Ищет промпт по раскладкам репозитория и образа — см. persona/enrich.py."""
    here = Path(__file__).resolve()
    for parent in here.parents[:6]:
        candidate = parent / "prompts" / name
        if candidate.exists():
            return candidate
    return here.parents[4] / "prompts" / name


SYSTEM_PROMPT_PATH = _find_prompt("respondent.system.md")
USER_PROMPT_PATH = _find_prompt("respondent.user.md")


class RespondentClient(Protocol):
    """Шов между прогоном и провайдером. system и user раздельно — см. модульный докстринг."""

    def complete(self, *, system: str, user: str) -> str: ...


class QwenRespondentClient:
    """Боевой клиент: OpenAI-совместимый endpoint TimeWeb (Decision Log #1)."""

    def __init__(self, config: Any | None = None, model: str | None = None,
                 temperature: float = 0.9):
        from ..config import ModelConfig

        self.config = config or ModelConfig.from_env()
        self.model = model or self.config.text_model
        # Высокая температура здесь — не небрежность, а условие метрики
        # response_diversity. При temperature=0 двадцать персон с похожей DNA
        # дают почти совпадающий текст, и mode collapse становится свойством
        # настройки, а не модели. Воспроизводимость прогона обеспечивается
        # снимком промптов и seed персоны, а не детерминизмом ответа.
        self.temperature = temperature

    def complete(self, *, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            default_headers=self.config.default_headers,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
        )
        return (response.choices[0].message.content or "").strip()


# ─── Сборка среза ────────────────────────────────────────────────────────────


def build_slice(
    persona: dict[str, Any],
    pack: dict[str, Any],
    survey: dict[str, Any],
    *,
    system_template: str,
    user_template: str,
) -> tuple[str, str]:
    """
    Собирает срез одной персоны: (system, user).

    Чистая функция: ничего не хранит между вызовами и ничего не меняет во
    входных объектах. Это и есть механизм изоляции — не проверка на выходе, а
    отсутствие места, где чужие данные могли бы задержаться.
    """
    dna = persona.get("dna", {})
    demographics = dna.get("demographics", {})
    lifestyle = dna.get("lifestyle_and_interests", {})

    system = (
        system_template
        .replace("{{persona_dna}}", json.dumps(dna, ensure_ascii=False, indent=2))
        .replace("{{segment}}", str(demographics.get("age_group", "не указан")))
        .replace("{{verbatim_examples}}", str(dna.get("narrative", "")))
        .replace("{{score_priors}}", "средние по реальной аудитории: 6–8 из 10")
    )

    user = (
        user_template
        .replace("{{video_understanding}}", json.dumps(pack, ensure_ascii=False, indent=2))
        .replace("{{survey_questions}}", _render_questions(survey))
        .replace("{{content_title}}", str(pack.get("title", "материал")))
    )
    _ = lifestyle  # оставлено намеренно: расширение среза идёт сюда, а не в промпт
    return system, user


def _render_questions(survey: dict[str, Any]) -> str:
    questions = survey.get("questions") or []
    lines = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        lines.append(f"- [{q.get('id', '?')}] ({q.get('type', 'открытый')}) {q.get('text', '')}")
    return "\n".join(lines) if lines else "(анкета пуста)"


# ─── Разбор ответа ───────────────────────────────────────────────────────────

_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$")


def parse_answer(text: str) -> dict[str, Any]:
    """
    Разбирает JSON-ответ персоны.

    Модель регулярно оборачивает JSON в ```json — это обычное поведение
    чат-модели, а не сбой, и падать на трёх кавычках значило бы терять
    оплаченный ответ. Тот же приём, что в frames/analyze.py.
    """
    body = _FENCE.sub("", text.strip())
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("ответ персоны не является объектом")
    return parsed


# ─── Результат ───────────────────────────────────────────────────────────────


@dataclass
class SurveyOutcome:
    """Итог прогона. Отказы считаются: отчёт обязан знать, на скольких ответах он стоит."""

    answers: list[dict[str, Any]] = field(default_factory=list)
    failures: int = 0
    failure_reasons: list[str] = field(default_factory=list)
    diversity: dict[str, Any] = field(default_factory=dict)


# ─── Прогон ──────────────────────────────────────────────────────────────────


def run_survey(
    *,
    personas: list[dict[str, Any]],
    pack: dict[str, Any],
    survey: dict[str, Any],
    client: RespondentClient,
    replication_count: int = 1,
    artifact_path: Path | None = None,
    system_template: str | None = None,
    user_template: str | None = None,
) -> SurveyOutcome:
    """
    Прогоняет каждую персону через анкету replication_count раз.

    `replication_count` — «Перекрытие» из #11: одна и та же персона отвечает
    несколько раз, и разброс её собственных ответов показывает, сколько в оценке
    шума модели, а сколько — позиции персоны. Повторы независимы: персона не
    видит своих прежних ответов, иначе второй ответ был бы согласован с первым
    по построению и разброс перестал бы что-либо мерить.
    """
    if system_template is None:
        system_template = (
            SYSTEM_PROMPT_PATH.read_text("utf-8") if SYSTEM_PROMPT_PATH.exists() else ""
        )
    if user_template is None:
        user_template = (
            USER_PROMPT_PATH.read_text("utf-8") if USER_PROMPT_PATH.exists() else ""
        )

    outcome = SurveyOutcome()

    # Порядок обхода: персона за персоной, репликация за репликацией, партиями
    # по BATCH_SIZE. Партия — единица прогресса и единица отказоустойчивости.
    tasks = [
        (persona, rep)
        for persona in personas
        for rep in range(replication_count)
    ]

    for start in range(0, len(tasks), BATCH_SIZE):
        for persona, rep in tasks[start:start + BATCH_SIZE]:
            system, user = build_slice(
                persona, pack, survey,
                system_template=system_template, user_template=user_template,
            )
            try:
                raw = client.complete(system=system, user=user)
                answer = parse_answer(raw)
            except Exception as exc:
                outcome.failures += 1
                outcome.failure_reasons.append(
                    f"{persona.get('id', '?')} (повтор {rep}): {type(exc).__name__}: {exc}"
                )
                continue
            outcome.answers.append({
                "persona_id": persona.get("id"),
                "persona_name": persona.get("name"),
                "replication": rep,
                "answer": answer,
            })

    outcome.diversity = diversity_report(outcome.answers)

    if artifact_path is not None:
        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "answers": outcome.answers,
                    "failures": outcome.failures,
                    "failure_reasons": outcome.failure_reasons,
                    "diversity": outcome.diversity,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "utf-8",
        )

    return outcome
