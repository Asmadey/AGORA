"""
Одно место, где известно, какой формы бывает анкета.

─── Почему модуль появился ──────────────────────────────────────────────────
Анкета приезжает в очередь тем, чем лежит в колонке `surveys.questions`, — то
есть СПИСКОМ вопросов. Внутри воркера её читали как словарь `{"questions": …}`
в двух местах независимо, и оба падали с `'list' object has no attribute 'get'`:
сначала `respondent/run.py` на 344-й секунде прогона, потом, после починки
первого, `qa/checks.py` на 690-й.

Второе падение — урок про заплатки. Починенное место перестало падать, и
следующее по конвейеру стало новым «первым». Правка по месту не уменьшает число
таких мест, она только отодвигает встречу с ними — и каждая встреча стоит
полного прогона: расшифровки, разбора кадров и опроса персон.

Поэтому знание о форме живёт здесь одно, а `test_survey_contract.py` статически
требует, чтобы никто не читал анкету мимо этих функций.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "survey_questions",
    "question_label",
    "question_options",
    "question_rows",
    "answerable_fields",
    "render_questions",
    "MATRIX_TYPES",
    "CLOSED_TYPES",
]


def survey_questions(survey: Any) -> list[dict[str, Any]]:
    """
    Вопросы анкеты списком, какой бы формы ни пришла анкета.

    Канон — список: именно его кладёт в очередь `POST /api/tasks`. Словарь
    `{"questions": [...]}` принимается ради фикстур CDD и ручных прогонов;
    расхождения это не создаёт, потому что обе формы сводятся к одному списку.

    Всё остальное — пустой список, а не исключение: анкета необязательна,
    прогон без неё законен и идёт по пяти базовым критериям.
    """
    if isinstance(survey, dict):
        raw = survey.get("questions")
    elif isinstance(survey, list):
        raw = survey
    else:
        raw = None

    if not isinstance(raw, list):
        return []
    return [q for q in raw if isinstance(q, dict)]


def question_label(question: dict[str, Any]) -> str:
    """
    Формулировка вопроса.

    В контракте продукта поле называется `label` — так в `agora-types.ts`, в
    JSON Schema анкеты и в конструкторе. Воркер читал `text`, которого там нет,
    и получал пустые строки. Это опаснее отказа: прогон проходит целиком, стоит
    полную цену и даёт ответы на вопросы, которых персона не видела.

    `text` оставлен запасным ключом ради старых записей в базе, но первым идёт
    контракт, а не догадка.
    """
    return str(question.get("label") or question.get("text") or "").strip()


# ─── Закрытые вопросы ────────────────────────────────────────────────────────
#
# Анкета заказчика (data/survey/customer_2026.json) принесла четыре формы,
# которых у продукта не было: выбор одного из списка, выбор нескольких с
# потолком, матрица «строка × вариант» и служебные варианты, выбираемые в
# одиночку. Знание об этих формах живёт ЗДЕСЬ по той же причине, по которой
# здесь живёт `survey_questions`: разбор анкеты по месту уже дважды ронял
# прогон на 344-й и 690-й секунде, и второе падение нашлось только после
# починки первого.

#: Типы, у которых ответ даётся по каждой СТРОКЕ, а не по вопросу целиком.
MATRIX_TYPES = frozenset({"matrix_single"})

#: Типы, у которых ответ обязан быть одним из объявленных вариантов.
CLOSED_TYPES = frozenset({"single_choice", "multi_choice", "matrix_single"})


def question_options(question: dict[str, Any]) -> list[dict[str, Any]]:
    """Варианты ответа. Пусто у шкал и открытых вопросов."""
    raw = question.get("options")
    return [o for o in raw if isinstance(o, dict)] if isinstance(raw, list) else []


def question_rows(question: dict[str, Any]) -> list[dict[str, Any]]:
    """Строки матрицы. Пусто у всех остальных типов."""
    raw = question.get("rows")
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


def answerable_fields(survey: Any) -> list[str]:
    """
    Адреса всего, на что персона обязана ответить.

    Матрица — это не один ответ, а по ответу на строку: сорок три подтемы
    вопроса 9 и одиннадцать подвопросов вопроса 11 дают пятьдесят четыре поля
    из одного «вопроса». Считать их за два — значит считать покрытие анкеты
    неправильно и не заметить, что персона пропустила сорок ответов.

    Адрес матричного поля — `<идентификатор вопроса>/<идентификатор строки>`.
    """
    out: list[str] = []
    for question in survey_questions(survey):
        qid = str(question.get("id") or "").strip()
        if not qid:
            continue
        if str(question.get("type")) in MATRIX_TYPES:
            out.extend(f"{qid}/{row.get('id')}" for row in question_rows(question))
        else:
            out.append(qid)
    return out


def _option_line(index: int, option: dict[str, Any], exclusive: set[str]) -> str:
    label = str(option.get("label") or "").strip()
    alone = " — выбирается только сам по себе, без других вариантов"
    mark = alone if str(option.get("id")) in exclusive else ""
    return f"  {index}) [{option.get('id')}] {label}{mark}"


def render_questions(survey: Any) -> str:
    """
    Анкета в текст для промпта респондента.

    Закрытый вопрос БЕЗ своих вариантов — это открытый вопрос: модель ответит
    правдоподобно и мимо списка, диаграмма не соберётся, а в логе прогона всё
    будет выглядеть исправным. Поэтому варианты, строки матрицы, потолок выбора
    и правило одиночного выбора печатаются здесь, а не подразумеваются.

    Формулировка вопроса стоит дословно: `respondent/run.py:_asked_questions`
    сверяет промпт с анкетой именно по ней и отказывается от прогона, если
    вопрос до промпта не доехал.
    """
    blocks: list[str] = []
    for question in survey_questions(survey):
        qid = question.get("id", "?")
        qtype = str(question.get("type") or "open")
        label = question_label(question)
        options = question_options(question)
        rows = question_rows(question)
        exclusive = {str(i) for i in (question.get("exclusiveOptionIds") or [])}

        if qtype == "scale":
            head = f"[{qid}] шкала {question.get('scaleMin', 0)}–{question.get('scaleMax', 10)}"
        elif qtype == "single_choice":
            head = f"[{qid}] выбери ровно один вариант"
        elif qtype == "multi_choice":
            cap = question.get("maxChoices")
            head = f"[{qid}] выбери не более {cap} вариантов" if cap \
                else f"[{qid}] выбери один или несколько вариантов"
        elif qtype in MATRIX_TYPES:
            head = f"[{qid}] ответь по каждой строке, по одному варианту на строку"
        else:
            head = f"[{qid}] ответь текстом"

        lines = [head, label]

        if options and qtype in MATRIX_TYPES:
            lines.append("Варианты для каждой строки:")
            lines.extend(_option_line(i + 1, o, exclusive) for i, o in enumerate(options))
        elif options:
            lines.extend(_option_line(i + 1, o, exclusive) for i, o in enumerate(options))

        if rows:
            themes = {
                str(t.get("id")): str(t.get("label") or "")
                for t in (question.get("themes") or [])
            }
            current = None
            lines.append("Строки:")
            for row in rows:
                theme_id = str(row.get("themeId") or "")
                if theme_id and theme_id != current and theme_id in themes:
                    lines.append(f"  {themes[theme_id]}")
                    current = theme_id
                lines.append(f"    [{row.get('id')}] {str(row.get('label') or '').strip()}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) if blocks else "(анкета пуста)"
