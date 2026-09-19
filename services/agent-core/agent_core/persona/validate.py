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

Замер до правки на боевых наборах показывает, почему порог нельзя крутить
вместо исправления инструкции: 11.09 были пересозданы 14 из 40 персон (35%),
16.09 - 8 из 20 (40%), ещё один набор 16.09 - 5 из 10 (50%). В среднем было
1.50, 1.60 и 1.80 попытки соответственно; после трёх наборов несвязными
оставались 2, 2 и 0 персон.

Разбор 74 претензий разделил их на три качественных класса: класс 1 - около
27 случаев, когда атрибут не упомянут в тексте; класс 2 - настоящие
противоречия текста атрибутам, которые проверка должна ловить; класс 3 -
претензии к несовместимым между собой полям скелета, которые генератор
сэмплирует независимо и которые не являются дефектом текста.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..prompt_text import body_of

#: Сколько раз пересоздавать персону, не прошедшую проверку.
#:
#: Три — не круглое число из воздуха: одна попытка не отличает случайную
#: неудачу модели от неописуемого сочетания атрибутов, а после третьей
#: вероятность, что дело в модели, уже мала — и дальше мы просто платим за
#: генерацию, которая не сойдётся.
MAX_ATTEMPTS = 3

#: Ниже этой уверенности вердикт «несвязна» не принимается.
#:
#: Было 0.5, стало 0.9 — по решению владельца и по существу дела.
#:
#: Персона — розыгрыш из распределений корпуса, а не его копия. То, что она
#: вышла «немного другой», и есть работа генератора: смысл синтетической
#: аудитории в покрытии пространства, а не в повторении выборки. Отбраковка за
#: непохожесть уничтожает ровно то, ради чего продукт существует, и делает это
#: дорого — каждая попытка оплачена.
#:
#: Проверка остаётся, но ловит только то, ради чего заводилась: прямое
#: противоречие текста своим же атрибутам («не смотрю сериалы» при ежедневном
#: просмотре). Цена ошибок несимметрична, и порог это отражает: ложная
#: отбраковка стоит трёх перегенераций, пропуск — одного странного портрета,
#: который видно глазами.
MIN_CONFIDENCE = 0.9

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
    # В ответе модели это список объектов с kind, severity и message. Строки
    # сохраняются только для старых арендаторов и тестовых клиентов, которые
    # ещё отвечают до включения строгой схемы.
    issues: list[Any] = field(default_factory=list)
    confidence: float = 0.0
    #: Проверка не состоялась — модель недоступна или ответ не разобрался.
    #: Это НЕ то же самое, что «связна»: неизвестность обязана быть видна.
    checked: bool = True
    attempts: int = 1
    #: Вердикт ПЕРВОЙ попытки, если персону пересоздавали. None — прошла сразу.
    #:
    #: Финальный вердикт описывает персону, которая лежит в наборе; первый —
    #: ту, которой в наборе нет. Без него нельзя ответить, ЗА ЧТО бракуют: в
    #: базу попадал вердикт уже прошедшей замены, а претензия, из-за которой
    #: предыдущую выбросили, исчезала вместе с ней.
    first: Verdict | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "checked": self.checked,
            "consistent": self.consistent,
            "issues": self.issues,
            "confidence": self.confidence,
            "attempts": self.attempts,
        }
        if self.first is not None:
            # Без рекурсии вглубь: у первого вердикта своего «первого» нет и
            # быть не может, а вложенность без дна раздувает строку в базе.
            payload["initial"] = {
                "checked": self.first.checked,
                "consistent": self.first.consistent,
                "issues": self.first.issues,
                "confidence": self.first.confidence,
            }
        return payload


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
        # Хвост, а не начало: обрыв виден только в конце, а по началу ответ
        # выглядит правильным. Первый же боевой набор потерял вердикт именно
        # так, и установить причину по записи не удалось — прежний срез на 200
        # символах отрезал ровно то место, где она была.
        body = text.strip()
        shown = body if len(body) <= 600 else f"{body[:200]} … {body[-400:]}"
        return Verdict(consistent=True, checked=False,
                       issues=[f"ответ проверяющего не разобран ({len(body)} симв.): {shown}"])
    if not isinstance(parsed, dict):
        return Verdict(consistent=True, checked=False,
                       issues=["ответ проверяющего не объект"])

    consistent = bool(parsed.get("consistent", True))
    raw_issues = parsed.get("issues") or []
    issues = list(raw_issues) if isinstance(raw_issues, list) else []
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
    # Служебная шапка снимается, как у всех прочих читателей промптов. До этой
    # правки «Переменные: {{skeleton_json}}, {{narrative}}, {{verbatim_pool}}»
    # подставлялась наравне с телом, и судья получал скелет, текст портрета и пул
    # реплик ПО ДВА РАЗА — причём первыми, до единой инструкции о том, что
    # считать расхождением. Модуль просто забыли внести в список читателей;
    # держит его теперь tests/test_prompt_header.py.
    template = body_of(template)
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
    reenriched: int = 0
    attribute_conflicts: int = 0
    failed: int = 0
    calls: int = 0

    @property
    def checked(self) -> int:
        return sum(1 for v in self.verdicts if v.checked)


_TEXT_ISSUE_KINDS = {"contradiction", "invented", "impersonal"}


def _issue_kind(issue: Any) -> str | None:
    """Возвращает тип структурированной претензии, если он есть."""
    return issue.get("kind") if isinstance(issue, dict) else None


def _is_attribute_conflict(issue: Any) -> bool:
    return _issue_kind(issue) == "attribute_conflict"


def _is_hard_text_issue(issue: Any) -> bool:
    # Строка означает старый ответ до миграции строгой схемы. Сохраняем его
    # старое безопасное поведение: явная строковая претензия считалась жёсткой.
    if isinstance(issue, str):
        return True
    return (
        isinstance(issue, dict)
        and issue.get("kind") in _TEXT_ISSUE_KINDS
        and issue.get("severity") == "hard"
    )


def _hard_text_issues(issues: list[Any]) -> list[Any]:
    return [issue for issue in issues if _is_hard_text_issue(issue)]


def validate_set(
    personas: list[dict[str, Any]],
    *,
    client: ValidatorClient,
    regenerate: Callable[[int, int], dict[str, Any] | None],
    reenrich: Callable[[int, list[Any]], dict[str, Any] | None] | None = None,
    template: str | None = None,
    verbatim_pool: list[str] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> ValidationOutcome:
    """
    Проверяет набор, сначала исправляя текст на том же скелете.

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
        # Первая попытка запоминается до цикла замен: дальше `verdict`
        # переприсваивается вердиктом замены, и претензия к исходной персоне
        # иначе теряется вместе с самой персоной.
        first = verdict

        result.attribute_conflicts += sum(
            1 for issue in first.issues if _is_attribute_conflict(issue)
        )

        # Переписывание имеет собственный бюджет: иначе три дешёвых попытки
        # на том же скелете исчезают из статистики, а новый seed берётся раньше
        # согласованного порога. После него действует прежний bounded loop для
        # действительно новой персоны.
        rewrite_attempts = 0
        while _hard_text_issues(verdict.issues) and reenrich is not None:
            if rewrite_attempts >= max_attempts:
                break
            issues = _hard_text_issues(verdict.issues)
            replacement = reenrich(index, issues)
            if replacement is None:
                break
            rewrite_attempts += 1
            attempt += 1
            current = replacement
            verdict = validate_persona(
                current, client=client, template=template, verbatim_pool=verbatim_pool
            )
            result.calls += 1
            result.reenriched += 1

        seed_attempts = 0
        while _hard_text_issues(verdict.issues) and seed_attempts < max_attempts - 1:
            seed_attempts += 1
            replacement = regenerate(index, seed_attempts)
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
        # Прикладываем первый вердикт только если персону действительно
        # меняли: у прошедшей сразу «первый» и «финальный» — один и тот же, и
        # дубль в базе отличить от настоящей отбраковки было бы нельзя.
        if attempt > 1:
            verdict.first = first
        # Мягкая претензия и конфликт атрибутов записываются, но не делают
        # персону failed: отказ касается только жёсткого дефекта текста.
        if _hard_text_issues(verdict.issues):
            result.failed += 1

        result.personas[index] = current
        result.verdicts.append(verdict)

    return result
