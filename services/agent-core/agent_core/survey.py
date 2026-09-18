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

from dataclasses import dataclass, field
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
    "FieldAnswer",
    "parse_field_answer",
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


def row_options(question: dict[str, Any], row: dict[str, Any] | None) -> list[dict[str, Any]]:
    """
    Варианты ответа строки матрицы: свои, а если своих нет — общие у вопроса.

    Оба случая живые. У вопроса 9 заказчика список один на все сорок три
    подтемы («поднималась / не поднималась / затрудняюсь»), и повторять его у
    каждой строки значило бы сорок три раза записать одно и то же. У своей
    матрицы оператора вопросы внутри темы разные, и общий список склеил бы их:
    персоне предложили бы варианты чужого вопроса, а её ответ разобрался бы
    против них же — молча и с правдоподобным результатом.

    Порядок «своё, иначе общее», а не слияние: слияние дало бы вопросу варианты,
    которых оператор ему не назначал.
    """
    raw = (row or {}).get("options")
    if isinstance(raw, list):
        own = [o for o in raw if isinstance(o, dict)]
        if own:
            return own
    return question_options(question)


def row_max_choices(question: dict[str, Any], row: dict[str, Any] | None) -> int:
    """
    Сколько вариантов персона выбирает в этой строке. По умолчанию — ровно один.

    Единица по умолчанию, а не «сколько угодно»: матрица заказчика отвечается по
    одному варианту на строку, и молчаливое разрешение выбрать больше сделало бы
    доли по строке несравнимыми с его полевыми волнами.
    """
    cap = (row or {}).get("maxChoices")
    return cap if isinstance(cap, int) and cap >= 1 else 1


def answerable_fields(survey: Any) -> list[str]:
    """
    Адреса всего, на что персона обязана ответить.

    Матрица — это не один ответ, а по ответу на строку: сорок три подтемы
    вопроса 9 и одиннадцать подвопросов вопроса 11 дают пятьдесят четыре поля
    из одного «вопроса». Считать их за два — значит считать покрытие анкеты
    неправильно и не заметить, что персона пропустила сорок ответов.

    ─── Адрес матричного поля — идентификатор СТРОКИ ────────────────────────
    Голый `t1-1`, а не пара `q09-themes/t1-1`. Здесь стояла пара, и это была
    четвёртая форма адреса в репозитории, которую не писал и не читал никто:
    промпт печатает строку как `[t1-1]` (`render_questions`), выгрузка и
    расчёты ищут ответ по голому идентификатору, правило покрытия — тоже.

    Проба нагрузки компенсировала расхождение делением строки по «/» — то есть
    дефект не был виден именно потому, что его обошли по месту. Замер «40 из
    67» от этого не пострадал, а функция как контракт была неверна.

    Совпадение с промптом держит `test_survey_render.py`: адрес поля обязан
    быть ровно тем, что промпт печатает в квадратных скобках.
    """
    out: list[str] = []
    for question in survey_questions(survey):
        qid = str(question.get("id") or "").strip()
        if not qid:
            continue
        if str(question.get("type")) in MATRIX_TYPES:
            out.extend(
                str(row.get("id")) for row in question_rows(question) if row.get("id")
            )
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
            head = (
                f"[{qid}] ответь по каждой строке; варианты и число ответов указаны у строки"
                if any(isinstance(r.get("options"), list) and r.get("options") for r in rows)
                else f"[{qid}] ответь по каждой строке, по одному варианту на строку"
            )
        else:
            head = f"[{qid}] ответь текстом"

        lines = [head, label]

        # Свой список хотя бы у одной строки означает, что общего списка у этой
        # матрицы нет: печатать его сверху значило бы предложить персоне
        # варианты, которых у конкретной строки не спрашивают.
        own_lists = any(isinstance(r.get("options"), list) and r.get("options") for r in rows)

        if options and qtype in MATRIX_TYPES and not own_lists:
            lines.append("Варианты для каждой строки:")
            lines.extend(_option_line(i + 1, o, exclusive) for i, o in enumerate(options))
        elif options and qtype not in MATRIX_TYPES:
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
                if not own_lists:
                    continue
                cap = row_max_choices(question, row)
                lines.append(
                    "      выбери ровно один вариант:" if cap == 1
                    else f"      выбери не более {cap} вариантов:"
                )
                lines.extend(
                    "  " + _option_line(i + 1, o, exclusive)
                    for i, o in enumerate(row_options(question, row))
                )

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) if blocks else "(анкета пуста)"


# ─── Разбор ответа ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FieldAnswer:
    """
    Разобранный ответ на одно поле анкеты.

    Поля разделены намеренно. `missing` — персона не ответила; `error` — она
    ответила, но не тем. Это разные вещи и разные решения: пропуск лечится
    переспросом, а чужой идентификатор — правкой промпта или списка.

    Молчаливое проглатывание опаснее обоих. Неразобранный вариант не попадёт ни
    в одну долю, доли сойдутся к ста процентам по оставшимся, и на графике это
    будет выглядеть мнением аудитории.
    """

    value: int | None = None
    option_ids: list[str] = field(default_factory=list)
    text: str = ""
    missing: bool = False
    error: str = ""


def _option_index(options: list[dict[str, Any]]) -> tuple[dict[str, str], set[str]]:
    """Сопоставление «идентификатор или подпись → идентификатор» и набор служебных."""
    by_key: dict[str, str] = {}
    service: set[str] = set()
    for option in options:
        oid = str(option.get("id") or "").strip()
        if not oid:
            continue
        by_key[oid.casefold()] = oid
        label = str(option.get("label") or "").strip()
        if label:
            by_key[label.casefold()] = oid
        if option.get("service"):
            service.add(oid)
    return by_key, service


def _chunks(raw: Any) -> list[str]:
    """Ответ как пришёл: список — поэлементно, строка — одним куском."""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    return [text] if text else []


def _resolve(chunk: str, by_key: dict[str, str]) -> tuple[list[str], list[str]]:
    """
    Разбор перечисления через запятую, когда запятая есть и внутри подписи.

    ─── Почему не простой split ─────────────────────────────────────────────
    Шесть из тринадцати эмоций анкеты заказчика названы парой: «Восхищение,
    восторг», «Тревога, страх». Промпт при этом велит перечислять выбранное
    через запятую — разделитель ответа совпадает с символом внутри подписи.
    Разбиение по запятой теряло такой ответ целиком и называло обе половины
    «вариантами не из списка», хотя персона выполнила инструкцию буквально.

    Правило: из каждой позиции берётся САМОЕ ДЛИННОЕ сочетание соседних
    кусков, которое есть в списке вариантов. «Восхищение, восторг, Гордость» —
    это `e-1` и `e-3`, а «Гордость, Надежда» — `e-3` и `e-5`, потому что такой
    пары в списке нет.

    Правило однозначно ровно пока ни одна половина парной подписи не
    совпадает с отдельным вариантом. В анкете заказчика это выполнено
    (проверено 17.09.2026), и держит это `test_customer_survey.py`: если
    заказчик пришлёт вариант «Восхищение» рядом с «Восхищение, восторг»,
    тест покраснеет до того, как разбор начнёт угадывать.
    """
    parts = [part.strip() for part in chunk.split(",") if part.strip()]
    picked: list[str] = []
    unknown: list[str] = []
    i = 0
    while i < len(parts):
        for j in range(len(parts), i, -1):
            oid = by_key.get(", ".join(parts[i:j]).casefold())
            if oid is not None:
                picked.append(oid)
                i = j
                break
        else:
            unknown.append(parts[i])
            i += 1
    return picked, unknown


def parse_field_answer(
    question: dict[str, Any], raw: Any, row: dict[str, Any] | None = None
) -> FieldAnswer:
    """
    Приводит ответ персоны к типу вопроса.

    ─── Почему разбор здесь, а не у читателя ────────────────────────────────
    В этом репозитории ответ персоны уже разбирали по месту в четырёх местах, и
    каждое расходилось с остальными по-своему: `report-view.ts` до сих пор
    ищет ответ четырьмя запасными путями, `qa/checks.py` чинили дважды,
    `content/pack.py` один раз. Разбор в одном месте — единственный способ, при
    котором расхождение невозможно, а не отложено.

    ─── Почему подпись принимается наравне с идентификатором ────────────────
    Модель иногда называет вариант словами. Отвергнуть такой ответ значило бы
    потерять оплаченный ответ из-за формы, а подпись однозначна: сопоставление
    делается здесь, один раз.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return FieldAnswer(missing=True)

    qtype = str(question.get("type") or "open")

    if qtype == "open":
        return FieldAnswer(text=str(raw).strip())

    if qtype == "scale":
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            return FieldAnswer(error=f"балл не разобран: {raw!r}")
        low = int(question.get("scaleMin", 0))
        high = int(question.get("scaleMax", 10))
        if not low <= value <= high:
            return FieldAnswer(error=f"балл {value} вне шкалы {low}–{high}")
        return FieldAnswer(value=value)

    # Варианты берутся у СТРОКИ, когда она названа: у своей матрицы оператора
    # списки у вопросов внутри темы разные, и разбор против общего принял бы
    # чужой вариант как свой — без отказа и с правдоподобной долей на графике.
    by_key, service = _option_index(row_options(question, row))
    picked: list[str] = []
    unknown: list[str] = []
    for chunk in _chunks(raw):
        found, missed = _resolve(chunk, by_key)
        picked.extend(oid for oid in found if oid not in picked)
        unknown.extend(missed)

    problems: list[str] = []
    if unknown:
        problems.append("варианты не из списка: " + ", ".join(unknown))

    if qtype in MATRIX_TYPES:
        cap = row_max_choices(question, row)
    else:
        cap = question.get("maxChoices") if qtype == "multi_choice" else 1
    if isinstance(cap, int) and len(picked) > cap:
        problems.append(
            f"выбрано {len(picked)} вариантов, потолок — не более {cap}"
        )

    chosen_service = [oid for oid in picked if oid in service]
    if chosen_service and len(picked) > 1:
        problems.append(
            f"вариант {chosen_service[0]} выбирается только сам по себе, без других"
        )

    return FieldAnswer(option_ids=picked, error="; ".join(problems))
