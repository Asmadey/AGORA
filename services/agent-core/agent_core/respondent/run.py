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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..prompt_text import body_of
from ..survey import question_label, survey_questions
from ..tracing import submit_in_context
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
                 temperature: float | None = None):
        from ..config import ModelConfig, TemperatureConfig

        self.config = config or ModelConfig.from_env()
        self.model = model or self.config.text_model
        # Стадия responseSimulation, умолчание 0.3.
        #
        # Прежде здесь стояло 0.9 как условие метрики response_diversity: при
        # температуре около нуля двадцать персон с похожей DNA дают почти
        # совпадающий текст, и mode collapse становится свойством настройки, а
        # не модели. Это по-прежнему верно, и потому значение вынесено в
        # настройки, а не заменено молча: у понижения есть цена, и платить её
        # должен тот, кто выбирает. Правило `diversity` в QA бракует
        # схлопнувшиеся ответы группами — если доля выживших упадёт после
        # понижения, причину искать здесь.
        #
        # Воспроизводимость прогона держится снимком промптов и seed персоны, а
        # не детерминизмом ответа.
        self.temperature = (
            TemperatureConfig.defaults().responseSimulation
            if temperature is None
            else temperature
        )

    def complete(self, *, system: str, user: str) -> str:
        from ..schemas.responses import MAX_TOKENS, content_of
        from ..tracing import llm_client

        # Клиент выдаётся agent_core.tracing: там он оборачивается для
        # LangFuse, если трассировка включена, и остаётся обычным, если нет.
        client = llm_client(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            default_headers=self.config.default_headers,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response = client.chat.completions.create(
            # Имя наблюдения в трассе. Без него интеграция назовёт
            # генерацию `OpenAI-generation` — одинаково для ответа
            # персоны, вердикта судьи и разбора кадра.
            name="answer-survey",
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            # ─── Почему ЗДЕСЬ строгой схемы нет ─────────────────────────
            #
            # Она тут была и делала хуже. Замер на двенадцати боевых персонах,
            # один и тот же промпт, температура 0.3, бок о бок:
            #
            #     со схемой   8 из 12 разобрано
            #     без схемы  12 из 12 разобрано
            #
            # Четыре ответа вырождались под грамматикой: после нормального
            # начала модель залипала — то на пробельных токенах (JSON их
            # разрешает между значениями), то на счётчике внутри строки
            # («, 4, 5, 6, … 675») — и шла до потолка, не дописав JSON.
            # Вырождение случайное: те же четыре персоны в другом прогоне
            # проходили целиком.
            #
            # Схема остаётся там, где форма мелкая и фиксированная: разбор
            # кадра, вердикты QA, валидация персоны. У ответа персоны структура
            # крупная, с открытыми массивами и свободным текстом — грамматике
            # есть где заблудиться, и цена блуждания здесь максимальна: теряется
            # не поле, а весь оплаченный ответ.
            #
            # Покрытие анкеты, ради которого схема и вводилась, держит правило
            # `consistency` в QA: оно называет пропущенный вопрос поимённо. Это
            # слабее гарантии по построению, но двенадцать ответов с проверкой
            # покрытия полезнее восьми с гарантией.
            max_tokens=MAX_TOKENS["respondent"],
            # Размышление выключено: см. ModelConfig.thinking — замер и причина.
            extra_body=self.config.extra_body("respondent"),
        )
        return content_of(response, role="respondent")


# ─── Сборка среза ────────────────────────────────────────────────────────────


def _segment_of(persona: dict[str, Any]) -> dict[str, str]:
    """
    Три поля DNA, по которым отчёт режет аудиторию на группы.

    Копия, а не ссылка на персону: карточка ответа переживает прогон и уезжает в
    Mongo, а состав аудитории — нет. Считать разрез задним числом по сохранённым
    ответам было бы нечем, если бы срез не лёг рядом с ответом сразу.

    Дублирование трёх полей — сознательная плата. Альтернатива, соединять ответы
    с персонами при чтении отчёта, ломается ровно там, где нужна: персону
    отредактировали или удалили, а отчёт обязан показывать ту аудиторию, на
    которой его посчитали.
    """
    from ..analytics.aggregate import SEGMENT_DIMENSIONS

    demographics = (persona.get("dna") or {}).get("demographics") or {}
    return {
        field: str(demographics[field])
        for field in SEGMENT_DIMENSIONS
        if demographics.get(field)
    }


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


def _render_questions(survey: Any) -> str:
    """
    Анкета в текст для промпта респондента.

    Форму и имя поля разбирает `agent_core.survey` — единственное место, где
    это знание живёт. Раньше разбор был здесь по месту, и после его починки
    ровно тот же дефект нашёлся в `qa/checks.py`: заплатка не уменьшает число
    мест, она только отодвигает встречу со следующим.
    """
    lines = []
    for q in survey_questions(survey):
        label = question_label(q)
        lines.append(f"- [{q.get('id', '?')}] ({q.get('type', 'открытый')}) {label}".rstrip())
    return "\n".join(lines) if lines else "(анкета пуста)"


def _asked_questions(user_prompt: str, survey: Any) -> list[dict[str, Any]]:
    """
    Какие вопросы действительно оказались в промпте. Иначе — отказ.

    Читается из собранной строки, а не из анкеты: смысл поля именно в том,
    чтобы поймать случай «анкета есть, в промпте её нет». Список, собранный из
    аргумента, подтвердил бы сам себя.

    Пустая анкета — законное состояние: прогон идёт по пяти базовым критериям
    из формата ответа. Поэтому пусто здесь значит пусто, а не отказ.
    """
    questions = survey_questions(survey)
    if not questions:
        return []

    missing = [q for q in questions if question_label(q) not in user_prompt]
    if missing:
        ids = ", ".join(str(q.get("id", "?")) for q in missing)
        hint = (
            "в шаблоне нет метки {{survey_questions}} — подстановка строкой "
            "молча не сработала"
            if "{{survey_questions}}" not in user_prompt
            and "(анкета пуста)" not in user_prompt
            else "формулировки не дошли до промпта"
        )
        raise ValueError(
            f"анкета не доехала до персоны ({hint}); не заданы вопросы: {ids}. "
            f"Прогон остановлен до первого обращения к модели: персоны заполнили бы "
            f"survey_answers по формату ответа, придумав вопросы сами, и отчёт "
            f"выглядел бы обычным."
        )

    return [
        {
            "id": q.get("id"),
            "label": question_label(q),
            "type": q.get("type", "открытый"),
            # Ответ на базовый вопрос промпт кладёт в `scores`, а не в
            # `survey_answers`. Без этого поля отчёт ищет его не там и рисует
            # «не ответила» рядом с нарисованным баллом — читатель делает вывод,
            # что прогон ненастоящий.
            "baseKey": q.get("baseKey"),
        }
        for q in questions
    ]


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
    # Только если поле есть: подставлять пустой словарь там, где модель ничего
    # не вернула, значит стирать разницу между «ответов нет» и «поля нет», а
    # правило покрытия эти случаи различает.
    if "survey_answers" in parsed:
        parsed["survey_answers"] = _answers_to_map(parsed["survey_answers"])
    _normalize_perception(parsed)
    return parsed


def _normalize_perception(parsed: dict[str, Any]) -> None:
    """
    Приводит «досмотрит» к словарю корпуса, сохраняя сказанное моделью.

    Здесь, сразу после разбора, по той же причине, что и `_answers_to_map`:
    иначе приведение расползлось бы по правилам QA, агрегату и карточке
    персоны — трём местам, которые разъедутся при первой правке.

    Приведение, а не ограничение провайдера: строгая схема для ответа персоны
    выключена по замеру (8 разобранных из 12 против 12 из 12), и ограничить
    формулировку на входе нечем. Разбор причины — в agent_core/schemas/answer.py.
    """
    from ..schemas.answer import normalize_retention

    perception = parsed.get("perception")
    if not isinstance(perception, dict) or "retention_intent" not in perception:
        return

    out = normalize_retention(perception.get("retention_intent"))
    # Исходная строка кладётся рядом ВСЕГДА, а не только при расхождении: по
    # ней видно, что промпт разошёлся с моделью, и видно это в данных прогона, а
    # не в чьей-то памяти.
    perception["retention_intent_raw"] = out.raw
    if out.value is not None:
        perception["retention_intent"] = out.value


def _answers_to_map(raw: Any) -> dict[str, Any]:
    """
    Приводит ответы анкеты к словарю «вопрос → ответ».

    По схеме строгого режима они приезжают СПИСКОМ ПАР: словарь с произвольными
    ключами там невыразим — `additionalProperties: false` и «ключи заранее
    неизвестны» противоречат друг другу.

    Приведение стоит здесь, сразу после разбора, чтобы всё ниже по течению —
    правила покрытия в `qa/checks.py`, карточка персоны в отчёте — устройства
    не заметило. Иначе смена формата ответа расползлась бы по трём слоям ради
    ограничения провайдера.

    Словарь на входе принимается как есть: так отвечали персоны до перехода на
    схему, и перечитывание старых прогонов (#30) не должно на этом падать.
    """
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, list):
        return {}
    out: dict[str, Any] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if question:
            out[question] = item.get("answer")
    return out


# ─── Результат ───────────────────────────────────────────────────────────────


@dataclass
class SurveyOutcome:
    """Итог прогона. Отказы считаются: отчёт обязан знать, на скольких ответах он стоит."""

    answers: list[dict[str, Any]] = field(default_factory=list)
    failures: int = 0
    failure_reasons: list[str] = field(default_factory=list)
    diversity: dict[str, Any] = field(default_factory=dict)
    #: Вопросы, которые действительно ушли в промпт: [{id, label, type}].
    #:
    #: Не копия анкеты из аргумента, а то, что найдено в собранном user-промпте.
    #: Разница существенна ровно в том случае, ради которого поле заведено:
    #: анкета есть, а в промпт она не попала. И отдельно — анкету могли
    #: отредактировать после прогона, а отчёт обязан показывать заданное тогда.
    asked: list[dict[str, Any]] = field(default_factory=list)


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
            body_of(SYSTEM_PROMPT_PATH.read_text("utf-8"))
            if SYSTEM_PROMPT_PATH.exists() else ""
        )
    if user_template is None:
        user_template = (
            body_of(USER_PROMPT_PATH.read_text("utf-8"))
            if USER_PROMPT_PATH.exists() else ""
        )

    outcome = SurveyOutcome()

    # ── Анкета доехала до промпта? Проверяется ДО первого вызова модели ──────
    #
    # Подстановка идёт строкой: нет метки — `str.replace` молча ничего не
    # делает. Прогон при этом проходит целиком и стоит полную цену, а персоны
    # заполняют `survey_answers` по формату ответа, придумав вопросы сами.
    # Отличить такой отчёт от честного по его содержимому нельзя.
    #
    # Поэтому здесь отказ, а не деградация: непотраченные деньги и внятная
    # причина лучше правдоподобного отчёта ни о чём. Проверка на первой персоне
    # — шаблон и анкета для всех одни, а разбирать шестьсот промптов ради
    # свойства шаблона незачем.
    if personas:
        probe_system, probe_user = build_slice(
            personas[0], pack, survey,
            system_template=system_template, user_template=user_template,
        )
        _ = probe_system
        outcome.asked = _asked_questions(probe_user, survey)

    # Порядок обхода: персона за персоной, репликация за репликацией, партиями
    # по BATCH_SIZE. Партия — единица прогресса и единица отказоустойчивости.
    tasks = [
        (persona, rep)
        for persona in personas
        for rep in range(replication_count)
    ]

    def ask(persona: dict[str, Any], rep: int) -> dict[str, Any]:
        """Один ответ. Чистая работа: ничего общего с соседями по пачке."""
        system, user = build_slice(
            persona, pack, survey,
            system_template=system_template, user_template=user_template,
        )
        return {
            "persona_id": persona.get("id"),
            "persona_name": persona.get("name"),
            "replication": rep,
            "segment": _segment_of(persona),
            "answer": parse_answer(client.complete(system=system, user=user)),
        }

    # ── Пачка опрашивается одновременно ──────────────────────────────────────
    #
    # Раньше цикл внутри пачки шёл последовательно, и двенадцать персон занимали
    # 366 секунд из 754 — больше всего в прогоне после того, как расшифровка
    # поехала параллельно. При этом каждая персона независима: её срез
    # собирается из собственной DNA, материала и анкеты, ответы друг на друга не
    # влияют.
    #
    # Изоляция от потоков не страдает и не требует ничего нового: `build_slice`
    # — чистая функция, она ничего не хранит между вызовами и ничего не меняет
    # во входных объектах. Общего изменяемого состояния, в котором могли бы
    # смешаться две персоны, просто нет — см. модульный докстринг.
    #
    # Пачка остаётся потолком одновременных обращений. Без потолка пятьсот
    # персон ушли бы к провайдеру разом: это 429 на большей части и оплаченные
    # повторы. Из «единицы прогресса и отказоустойчивости» она стала ещё и
    # единицей нагрузки.
    for start in range(0, len(tasks), BATCH_SIZE):
        chunk = tasks[start:start + BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=BATCH_SIZE, thread_name_prefix="ask") as pool:
            # submit_in_context, а не pool.submit: вместе с задачей в рабочий
            # поток переносится контекст трассы. Без него ответ персоны
            # становится отдельной трассой без прогона и арендатора — см.
            # agent_core/tracing.py.
            futures = [(submit_in_context(pool, ask, persona, rep), persona, rep)
                       for persona, rep in chunk]

            # Результаты забираются В ПОРЯДКЕ ОТПРАВКИ, а не по мере готовности:
            # иначе два прогона на одних входах дали бы разный порядок карточек,
            # и сравнить их построчно было бы нельзя — а сравнение прогонов и
            # есть смысл перезапуска исследования (#30).
            for future, persona, rep in futures:
                try:
                    outcome.answers.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    outcome.failures += 1
                    outcome.failure_reasons.append(
                        f"{persona.get('id', '?')} (повтор {rep}): "
                        f"{type(exc).__name__}: {exc}"
                    )

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
                    # Заданные вопросы лежат рядом с ответами, а не берутся из
                    # анкеты при чтении отчёта: анкету можно отредактировать
                    # после прогона, и тогда отчёт показывал бы не то, что
                    # спрашивали.
                    "asked": outcome.asked,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "utf-8",
        )

    return outcome
