#!/usr/bin/env python3
"""
Сколько анкета заказчика весит для одной персоны и что с ней происходит.

─── Зачем этот файл существует ───────────────────────────────────────────────
Владелец решил 17.09.2026 опрашивать персону ОДНИМ вызовом модели, как сейчас.
При всех десяти темах вопроса 9 персона отвечает на 67 полей, и это больше той
структуры, на которой строгая схема уже вырождалась: замер в
`respondent/run.py:127` дал 8 разобранных ответов из 12 против 12 из 12 без
схемы.

Отсюда два числа, которых нет ни у кого, и без которых любое следующее решение
будет выбором вслепую:

1. **Доля пропущенных полей.** Пропущенный вопрос ловится правилом
   `consistency` уже ПОСЛЕ оплаты ответа, а переспрос гоняет весь пакет
   материала заново с потолком 15 за прогон. Если пропусков единицы — делать
   ничего не надо. Если их десятки — потолок исчерпается на первых пятнадцати
   персонах, и остальные останутся неполными молча.

2. **Эхо ценностей.** У персоны в DNA лежат пять ценностей из семнадцати,
   выданных жребием при её создании. Вопрос 8 спрашивает, какие ценности
   стремились донести СОЗДАТЕЛИ. При одном вызове модель видит и то, и другое в
   одном промпте, и ответ может оказаться пересказом собственных ценностей
   персоны. Тогда главная диаграмма отчёта описывала бы наш генератор, а не
   материал. Это ровно тот дефект, что уже был найден в графике «Ценности
   ВЦИОМ»: он считает ценности из DNA и не меняется от смены ролика.

─── Чего этот скрипт НЕ делает ───────────────────────────────────────────────
Не правит ни промпт, ни конвейер. Он мерит то, что есть, и печатает числа.
Решение по числам принимает владелец — так записано в плане.

─── Запуск ───────────────────────────────────────────────────────────────────

    python3 evals/analysis/survey_load_probe.py
        Статическая часть: нагрузка анкеты. Работает где угодно, модель не
        нужна, к базе не ходит.

    python3 evals/analysis/survey_load_probe.py --live --pack-task <uuid> -n 20
        Живая часть: N персон, по одному вызову модели на персону. Нужны
        доступ к Mongo и к модели; без них — честный SKIP, а не выдуманный
        результат (§9).

Внутри образа воркера путь к пакету материала берётся из Mongo по task_id
завершённого прогона — там лежит полная форма (`content_packs`).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SURVEY_PATH = REPO / "data" / "survey" / "customer_2026.json"
sys.path.insert(0, str(REPO / "services" / "agent-core"))

from agent_core.survey import (
    answerable_fields,
    parse_field_answer,
    question_rows,
    render_questions,
    survey_questions,
)

#: Инструкция по формату ответа для закрытых типов.
#:
#: Живёт здесь, а не в `prompts/respondent.user.md`, намеренно: правка промпта
#: продукта проходит с ведома владельца (§10), а замер обязан состояться до
#: правок. Форма ответа здесь ровно та, которую предполагает план этапа 3, —
#: список пар «адрес поля → идентификатор варианта».
ANSWER_RULES = """
# Как отвечать на вопросы анкеты

- На КАЖДОЕ поле анкеты — ровно одна запись в `survey_answers`.
- У вопроса с вариантами в `answer` идёт идентификатор варианта в квадратных
  скобках, например `e-3`. Своими словами варианты не называй.
- У вопроса-матрицы отвечай ПОСТРОЧНО: в `question` — идентификатор строки
  (например `t1-1` или `imp-4`), в `answer` — идентификатор варианта.
- У шкалы в `answer` — целое число в объявленных границах.
- Пропущенное поле — брак ответа целиком.
"""


# ─── Статическая часть ───────────────────────────────────────────────────────


def load_survey() -> dict[str, Any]:
    if not SURVEY_PATH.exists():
        raise SystemExit(f"нет {SURVEY_PATH.relative_to(REPO)} — анкета не заведена")
    return json.loads(SURVEY_PATH.read_text("utf-8"))


def static_load(survey: dict[str, Any]) -> dict[str, Any]:
    questions = survey["questions"]
    fields = answerable_fields(questions)
    text = render_questions(questions)

    by_question: list[tuple[int, str, int]] = []
    for q in survey_questions(questions):
        rows = question_rows(q)
        by_question.append((q["number"], q["type"], len(rows) if rows else 1))

    return {
        "fields": len(fields),
        "chars": len(text),
        "questions": len(questions),
        "by_question": by_question,
    }


def print_static(load: dict[str, Any]) -> None:
    print("─── Нагрузка анкеты при всех десяти темах ───")
    print(f"вопросов:        {load['questions']}")
    print(f"полей к ответу:  {load['fields']}")
    print(f"знаков в анкете: {load['chars']}")
    print()
    print("  № тип                поля")
    for number, qtype, count in load["by_question"]:
        mark = "  ← матрица" if count > 1 else ""
        print(f"  {number:>2} {qtype:<18} {count:>4}{mark}")
    print()


# ─── Живая часть ─────────────────────────────────────────────────────────────


def _skip(reason: str) -> None:
    """Честный пропуск. Выдуманный результат хуже отсутствующего (§9)."""
    print(f"SKIP живая часть: {reason}")
    print("Статическая часть выше посчитана и от среды не зависит.")


def load_pack(task_id: str) -> tuple[dict[str, Any] | None, str]:
    """
    Пакет материала из Mongo. Возвращает (пакет, причина отказа).

    ─── Почему здесь НЕ проверяется переменная окружения ────────────────────
    Первая редакция спрашивала `MONGO_URL`, а `agent_core/mongo.py` читает
    `MONGODB_URL`. Замер уходил в SKIP на сервере, где база доступна, — то есть
    инструмент, написанный против семейства дефектов «писатель и читатель
    разошлись по имени», сам в него и попал.

    Второго имени переменной здесь больше нет: доступность проверяется
    попыткой, а имя знает ровно один модуль.
    """
    try:
        from agent_core.analytics.store import CONTENT_PACKS
        from agent_core.mongo import mongo_db

        doc = mongo_db()[CONTENT_PACKS].find_one({"task_id": task_id})
    except Exception as exc:  # noqa: BLE001
        return None, f"Mongo недоступна — {type(exc).__name__}: {exc}"
    pack = (doc or {}).get("pack")
    if not pack:
        return None, f"в content_packs нет пакета для task_id={task_id}"
    return pack, ""


def make_personas(n: int, seed: int) -> list[dict[str, Any]]:
    """
    Персоны берутся из генератора, а не из базы.

    Генерация детерминирована и бесплатна: один seed — один набор. Замер должен
    воспроизводиться, а набор из базы меняется вместе с базой.
    """
    from agent_core.persona.generator import GenerationConfig, PersonaGenerator

    generator = PersonaGenerator.from_corpus()
    config = GenerationConfig(size=n, seed=seed)
    return [{"id": f"probe-{i}", "name": name, "dna": dna}
            for i, (name, dna) in enumerate(generator.generate_named(config))]


def ask_one(persona: dict[str, Any], pack: dict[str, Any], questions: list[dict[str, Any]],
            client: Any) -> dict[str, Any] | None:
    from agent_core.respondent.run import build_slice, parse_answer

    system_template = (REPO / "prompts" / "respondent.system.md").read_text("utf-8")
    user_template = (REPO / "prompts" / "respondent.user.md").read_text("utf-8")
    from agent_core.prompt_text import body_of

    system, user = build_slice(
        persona, pack, questions,
        system_template=body_of(system_template),
        user_template=body_of(user_template) + ANSWER_RULES,
    )
    try:
        raw = client.complete(system=system, user=user)
    except Exception as exc:  # noqa: BLE001
        print(f"  {persona['id']}: вызов не удался — {type(exc).__name__}: {exc}")
        return None
    return parse_answer(raw)


def answered_keys(answer: dict[str, Any]) -> set[str]:
    """
    Адреса полей, на которые персона ответила.

    ─── Две формы, и обе законны ────────────────────────────────────────────
    Промпт объявляет `survey_answers` списком пар «вопрос → ответ», но модель
    возвращает и объект «идентификатор → ответ», а `respondent/run.py`
    (`_answers_to_map`) обе формы приводит к одной. Первая редакция счётчика
    читала только список и на объекте показала «закрыто 0 полей из 67» —
    притом что персона ответила на ВСЕ шестьдесят семь правильными
    идентификаторами.

    Это был третий дефект в этом же приборе и снова тот же класс: писатель и
    читатель разошлись в форме. Число «0 из 67» выглядело результатом замера и
    было артефактом чтения.

    ─── И четвёртый, той же породы ──────────────────────────────────────────
    Замер 17.09.2026 показал «закрыто 31.9 из 67» — и снова это было чтение, а
    не модель: тринадцать персон из двадцати ответили на матрицу ВЛОЖЕННЫМ
    объектом под идентификатором вопроса, а прибор искал сорок три поля рядом.

    Отсюда правило, которое стоило четырёх ошибок подряд: прибор не разбирает
    ответ сам. Он зовёт `_answers_to_map` — тот же код, которым ответ читает
    продукт. Свой разбор в приборе означает, что прибор меряет себя.
    """
    from agent_core.respondent.run import _answers_to_map

    return {str(k).strip() for k in _answers_to_map(answer.get("survey_answers"))}


def coverage(answer: dict[str, Any], fields: list[str]) -> tuple[int, list[str]]:
    """
    Сколько полей закрыто.

    Здесь стояло деление адреса по «/»: `answerable_fields` выдавала пару
    «вопрос/строка», а персона называет строку. Обход работал и ровно поэтому
    прятал расхождение — адрес поля разошёлся с тем, что печатает промпт, и
    увидеть это по числам было нельзя.

    Адрес теперь один (голый идентификатор строки), и обход снят: если формы
    разойдутся снова, покрытие честно упадёт, а не подстроится.
    """
    said = answered_keys(answer)
    missing = [field for field in fields if field not in said]
    return len(fields) - len(missing), missing


def answer_for(answer: dict[str, Any], field: str) -> Any:
    """Ответ на одно поле — через тот же разбор, что у продукта."""
    from agent_core.respondent.run import _answers_to_map

    return _answers_to_map(answer.get("survey_answers")).get(field)


def echo_test(pairs: list[tuple[set[str], set[str]]], rounds: int = 10000,
              seed: int = 20260917) -> dict[str, Any]:
    """
    Перестановочный тест: совпадают ли ответы на вопрос 8 с ценностями персоны
    чаще, чем при случайном сопоставлении.

    Статистика — среднее число совпадений на персону. Нулевая гипотеза: ответ
    не зависит от того, чьи ценности лежат рядом в промпте. Если p мал, эхо
    есть, и диаграмма вопроса 8 частично описывает наш генератор.
    """
    if len(pairs) < 5:
        return {"n": len(pairs), "p": None, "note": "мало наблюдений для теста"}

    # Ни одна персона не назвала ни одной ценности — мерить нечего. Перестановки
    # дадут p = 1.0, и это число прочтётся как «эха нет», хотя данных нет вовсе.
    if not any(said for _, said in pairs):
        return {
            "n": len(pairs),
            "p": None,
            "note": "ответов на вопрос 8 нет — эхо НЕ ИЗМЕРЕНО, а не отсутствует",
        }

    def stat(order: list[int]) -> float:
        return statistics.mean(
            len(pairs[i][0] & pairs[j][1]) for i, j in zip(range(len(pairs)), order)
        )

    observed = stat(list(range(len(pairs))))
    rng = random.Random(seed)
    idx = list(range(len(pairs)))
    hits = 0
    for _ in range(rounds):
        rng.shuffle(idx)
        if stat(idx) >= observed:
            hits += 1
    return {
        "n": len(pairs),
        "observed": round(observed, 3),
        "p": round((hits + 1) / (rounds + 1), 4),
    }


def live(args: argparse.Namespace, survey: dict[str, Any]) -> None:
    pack, refusal = load_pack(args.pack_task)
    if not pack:
        return _skip(refusal)

    try:
        from agent_core.config import ModelConfig
        from agent_core.respondent.run import QwenRespondentClient

        # Настройки БОЕВОГО прогона, а не умолчания библиотеки.
        #
        # ─── Почему это не мелочь ────────────────────────────────────────────
        # Первая редакция собирала клиент без настроек. Умолчание держит
        # `thinking_roles = {"respondent"}` (`config.py:86`), то есть оставляет
        # размышление ВКЛЮЧЁННЫМ, а в боевых настройках стоит
        # `reasoning.thinking = false`. По замеру в `schemas/responses.py`
        # размышление стоит 4738–4844 токена против 581–622 без него — почти
        # 5000 из 8000 уходили на рассуждение до первого токена ответа.
        #
        # Замер показывал обрывы по потолку и звал поднять потолок. Это был
        # дефект прибора, а не продукта: прибор мерил другую конфигурацию.
        # Ровно та ошибка, от которой предостерегает §9 — «одно объяснение на
        # два падения — это гипотеза, а не вывод».
        snapshot = json.loads(args.settings) if args.settings else {
            "reasoning": {"thinking": False},
        }
        schema = None
        if getattr(args, "schema", False):
            from agent_core.respondent.answer_schema import answer_json_schema

            schema = answer_json_schema(survey["questions"])
        client = QwenRespondentClient(
            config=ModelConfig.for_task(snapshot), answer_schema=schema,
        )
    except Exception as exc:  # noqa: BLE001
        return _skip(f"клиент модели не собрался: {type(exc).__name__}: {exc}")

    questions = survey["questions"]
    fields = answerable_fields(questions)
    personas = make_personas(args.n, args.seed)

    values_by_option = {
        o["id"]: o["label"]
        for q in questions if q["number"] == 8
        for o in q.get("options", [])
    }

    parsed = 0
    truncated = 0
    # Один ответ печатается целиком. Без него «закрыто 0 полей из 67» —
    # загадка, а не диагноз: неизвестно, ответила ли модель не туда, не тем
    # ключом или не ответила вовсе.
    sample_shown = [False]
    missing_total: Counter[str] = Counter()
    closed: list[int] = []
    sizes: list[int] = []
    echo_pairs: list[tuple[set[str], set[str]]] = []

    mode = "С ГРАММАТИКОЙ" if getattr(args, "schema", False) else "БЕЗ ГРАММАТИКИ"
    print(f"─── Живой замер [{mode}]: {len(personas)} персон, по одному вызову ───")
    for persona in personas:
        answer = ask_one(persona, pack, questions, client)
        if answer is None:
            truncated += 1
            continue
        if answer.get("parse_failed"):
            continue
        sizes.append(len(json.dumps(answer, ensure_ascii=False)))
        if sample_shown[0] is False:
            sample_shown[0] = True
            print("  ─ образец разобранного ответа ─")
            print("  " + json.dumps(answer, ensure_ascii=False, indent=2)[:1400]
                  .replace("\n", "\n  "))
            print("  ─ конец образца ─")
        parsed += 1
        done, missing = coverage(answer, fields)
        closed.append(done)
        missing_total.update(missing)

        own = set((persona["dna"].get("values_and_beliefs") or {}).get("important_values") or [])
        # Разбор — общим парсером, а не делением по запятой.
        #
        # Своё деление здесь было третьим в репозитории и ломалось об те же
        # подписи с запятой, что и остальные два. С грамматикой ответ вдобавок
        # приходит списком, а не строкой, — `parse_field_answer` знает обе
        # формы, а самодельное деление не знает ни одной надёжно.
        q08 = next((q for q in questions if q["number"] == 8), None)
        said = set()
        if q08 is not None:
            parsed_q8 = parse_field_answer(q08, answer_for(answer, "q08-values"))
            said = {values_by_option.get(oid, "") for oid in parsed_q8.option_ids}
        echo_pairs.append((own, said - {""}))

    print()
    print(f"разобрано ответов:  {parsed} из {len(personas)}")
    print(f"оборвано потолком:  {truncated}")
    if sizes:
        print(
            f"размер ответа:      {min(sizes)}–{max(sizes)} знаков, "
            f"медиана {int(statistics.median(sizes))}"
        )
    if closed:
        rate = statistics.mean(closed) / len(fields)
        print(f"закрыто полей:      {statistics.mean(closed):.1f} из {len(fields)} ({rate:.1%})")
        print(f"пропущено в среднем: {len(fields) - statistics.mean(closed):.1f} поля")
        print()
        print("  чаще всего пропускают:")
        for field, count in missing_total.most_common(10):
            print(f"    {field:<24} {count}")
    print()
    print("─── Эхо ценностей (вопрос 8 против DNA персоны) ───")
    print(json.dumps(echo_test(echo_pairs), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="прогнать персон через модель")
    parser.add_argument("--pack-task", default="", help="task_id прогона, чей пакет материала взять")
    parser.add_argument("-n", type=int, default=20, help="сколько персон опросить")
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument(
        "--schema", action="store_true",
        help=(
            "передать модели грамматику ответа (`respondent/answer_schema.py`). "
            "Без флага — как было до 17.09.2026. Замер имеет смысл ТОЛЬКО парой: "
            "два прогона одного кода на одних и тех же персонах и одном пакете"
        ),
    )
    parser.add_argument(
        "--settings", default="",
        help=(
            "снимок настроек прогона в JSON. По умолчанию берутся боевые: "
            'reasoning.thinking = false. Умолчания библиотеки НЕ годятся — они '
            "оставляют размышление включённым, и замер меряет не продукт"
        ),
    )
    args = parser.parse_args()

    survey = load_survey()
    print_static(static_load(survey))

    if not args.live:
        print("Живая часть не запрошена. Добавьте --live --pack-task <uuid>.")
        return
    if not args.pack_task:
        return _skip("не указан --pack-task")
    live(args, survey)


if __name__ == "__main__":
    main()
