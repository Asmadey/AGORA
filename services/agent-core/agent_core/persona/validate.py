"""
Фаза 2 генерации: проверка связности созданной персоны.

─── Зачем ───────────────────────────────────────────────────────────────────
Персона собирается в два шага. Первый — атрибуты: `generator.py` сэмплирует их
из долей корпуса через `random.Random(seed)`, модель не участвует вовсе. Второй
— `enrich.py`: модель переписывает атрибуты в связный портрет при температуре
`personaCreation` (умолчание 0.9).

Разброс на втором шаге задуман: без него двадцать персон с похожей DNA дают
почти совпадающий текст, и mode collapse становится свойством настройки, а не
модели. Но у разброса есть цена — текст может разойтись с атрибутами, из которых
собран, или досочинить биографию. Такая персона потом отвечает на анкету, и её
выдумка приезжает в отчёт как данные исследования.

─── Почему проверяется связность, а не соответствие датасету ────────────────
Спрашивать модель «соответствует ли персона датасету» бессмысленно: персона ПО
ПОСТРОЕНИЮ собрана из долей этого датасета, и ответ всегда будет «да». Такая
проверка зелена всегда и не ловит ничего — худший вид проверки, потому что
создаёт уверенность, не создавая гарантии.

Статистическое соответствие корпусу меряет метрика `persona_grounding`
(`evals/check.py`) — по распределениям, а не вызовом модели. Дублировать её
здесь незачем.

─── Что делает отказ ────────────────────────────────────────────────────────
Персона пересоздаётся с ДРУГИМ seed, до `MAX_ATTEMPTS` попыток. Другой seed, а
не повторный вызов модели на тех же атрибутах: расхождение могло прийти и от
самих атрибутов — редкое сочетание, которое связным текстом не описывается.

После исчерпания попыток персона остаётся в наборе с пометкой. Выбрасывать её
нельзя: набор заказанного размера — это то, что пользователь оплатил и на чём
строит выборку, а молчаливое сокращение смещает состав в сторону «удобных»
персон, то есть ровно тех, что перестают представлять корпус.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

#: Сколько раз пересоздавать персону, не прошедшую проверку.
#:
#: Три — не круглое число из воздуха: одна попытка не отличает случайную
#: неудачу модели от неописуемого сочетания атрибутов, а после третьей
#: вероятность, что дело в модели, уже мала — и дальше мы просто платим за
#: генерацию, которая не сойдётся.
MAX_ATTEMPTS = 3

#: Ниже этой уверенности вердикт «несвязна» не принимается.
#:
#: Промпт прямо велит при сомнении отвечать «связна» с низким confidence.
#: Порог — вторая линия на случай, если модель этой инструкции не послушалась:
#: ложное срабатывание стоит оплаченной перегенерации, пропуск — одного
#: странного ответа в отчёте, который видно глазами.
MIN_CONFIDENCE = 0.5

PROMPT_NAME = "persona.validate.md"


def _find_prompt() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "prompts" / PROMPT_NAME
        if candidate.exists():
            return candidate
    return here.parents[4] / "prompts" / PROMPT_NAME


class ValidatorClient(Protocol):
    """Тот же шов, что у остальных клиентов: подменяется в тестах целиком."""

    def complete(self, *, prompt: str) -> str: ...


@dataclass
class Verdict:
    """Итог проверки одной персоны."""

    consistent: bool
    issues: list[str] = field(default_factory=list)
    confidence: float = 0.0
    #: Проверка не состоялась — модель недоступна или ответ не разобрался.
    #: Это НЕ то же самое, что «связна»: неизвестность обязана быть видна.
    checked: bool = True
    attempts: int = 1

    def to_json(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "consistent": self.consistent,
            "issues": self.issues,
            "confidence": self.confidence,
            "attempts": self.attempts,
        }


def _parse(text: str) -> Verdict:
    """
    Разбор ответа модели.

    Обёртка в ```json — обычное поведение чат-модели, а не сбой; падать на трёх
    обратных кавычках значило бы терять оплаченный вызов.

    Неразобранный ответ даёт `checked=False`, а не «несвязна»: иначе сбой
    разбора выглядел бы как претензия к персоне и запускал бы перегенерацию,
    которая ничего не исправит.
    """
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return Verdict(consistent=True, checked=False,
                       issues=[f"ответ проверяющего не разобран: {text.strip()[:200]}"])
    if not isinstance(parsed, dict):
        return Verdict(consistent=True, checked=False,
                       issues=["ответ проверяющего не объект"])

    consistent = bool(parsed.get("consistent", True))
    raw_issues = parsed.get("issues") or []
    issues = [str(i) for i in raw_issues] if isinstance(raw_issues, list) else []
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    # Вердикт «несвязна» без уверенности не принимается — см. MIN_CONFIDENCE.
    if not consistent and confidence < MIN_CONFIDENCE:
        return Verdict(consistent=True, confidence=confidence,
                       issues=[f"претензия отклонена по уверенности {confidence:.2f}: "
                               + "; ".join(issues)])

    return Verdict(consistent=consistent, issues=issues, confidence=confidence)


def _render(template: str, persona: dict[str, Any], verbatim_pool: list[str]) -> str:
    skeleton = {k: v for k, v in persona.items() if k != "narrative"}
    return (
        template
        .replace("{{skeleton_json}}", json.dumps(skeleton, ensure_ascii=False, indent=2))
        .replace("{{narrative}}", str(persona.get("narrative") or ""))
        .replace("{{verbatim_pool}}", "\n".join(f"— {v}" for v in verbatim_pool[:20]))
    )


def validate_persona(
    persona: dict[str, Any],
    *,
    client: ValidatorClient,
    template: str | None = None,
    verbatim_pool: list[str] | None = None,
) -> Verdict:
    """Проверяет одну персону. Исключение клиента не выходит наружу."""
    if template is None:
        path = _find_prompt()
        template = path.read_text("utf-8") if path.exists() else ""
    if not template:
        return Verdict(consistent=True, checked=False,
                       issues=[f"промпт не найден: {PROMPT_NAME}"])

    try:
        answer = client.complete(prompt=_render(template, persona, verbatim_pool or []))
    except Exception as exc:  # noqa: BLE001 — недоступность модели не отказ фазы
        return Verdict(consistent=True, checked=False,
                       issues=[f"проверяющий недоступен: {type(exc).__name__}: {exc}"])
    return _parse(answer)


@dataclass
class ValidationOutcome:
    """Итог фазы по всему набору."""

    personas: list[dict[str, Any]]
    verdicts: list[Verdict]
    regenerated: int = 0
    failed: int = 0
    calls: int = 0

    @property
    def checked(self) -> int:
        return sum(1 for v in self.verdicts if v.checked)


def validate_set(
    personas: list[dict[str, Any]],
    *,
    client: ValidatorClient,
    regenerate: Callable[[int, int], dict[str, Any] | None],
    template: str | None = None,
    verbatim_pool: list[str] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> ValidationOutcome:
    """
    Проверяет набор, пересоздавая непрошедших.

    `regenerate(index, attempt)` обязан вернуть персону с ДРУГИМ seed либо None,
    если пересоздать нечем. Пересоздание вынесено наружу намеренно: здесь нет
    ни генератора, ни корпуса, ни слепка — и тащить их сюда значило бы связать
    проверку со способом создания.
    """
    if template is None:
        path = _find_prompt()
        template = path.read_text("utf-8") if path.exists() else ""

    result = ValidationOutcome(personas=list(personas), verdicts=[])

    for index, persona in enumerate(result.personas):
        attempt = 1
        current = persona
        verdict = validate_persona(
            current, client=client, template=template, verbatim_pool=verbatim_pool
        )
        result.calls += 1

        while not verdict.consistent and attempt < max_attempts:
            replacement = regenerate(index, attempt)
            if replacement is None:
                break
            attempt += 1
            current = replacement
            verdict = validate_persona(
                current, client=client, template=template, verbatim_pool=verbatim_pool
            )
            result.calls += 1
            result.regenerated += 1

        verdict.attempts = attempt
        if not verdict.consistent:
            result.failed += 1

        result.personas[index] = current
        result.verdicts.append(verdict)

    return result
