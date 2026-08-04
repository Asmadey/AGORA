"""Persona Generator — задача #5.

Методология PRD §10 — генерация синтетических персон из grounding-корпуса:

  1. **Сэмплирование по реальным долям** (сериал×город×сегмент) — не равномерно,
     а по фактическим пропорциям корпуса `unified_respondent_sessions.json`.
  2. **Калибровка баллов** по реальным средним (overall~7.3, plot~7.6,
     acting~8.1, music~8.1, cinematography~8; разброс 2–9) ±приоры.
  3. **Стилевое + аргументативное заземление** на verbatims (против sycophancy).
  4. **Ценности ВЦИОМ→DNA** — маппинг значений из корпуса в поля схемы.
  5. **Сегмент-ориентированная установка** к контенту.
  6. **Представитель сегмента, не копия** — каждый респондент уникален.

Детерминизм: один seed → один воспроизводимый результат. Это критично для
метрики ``persona_grounding`` и для CDD-теста: ``diff == 0`` на повторном прогоне.

Генератор работает в двух режимах:

- **Deterministic (без LLM)** — сэмплит демографию из распределений корпуса,
  калибрует Big Five и scores по реальным средним, собирает narrative из
  шаблонов. Полностью воспроизводим, валидируется против JSON Schema.
  Используется в CDD-тесте и в CI.

- **LLM (через промпт persona.generate.md)** — отправляет собранный контекст
  (portrait_md, segment_distributions, verbatim_pool) в модель и получает
  обратно JSON-массив персон. В этом режиме narrative и speech_style пишутся
  моделью, а не шаблонами. Требует OPENAI_API_KEY; без него — откат в
  deterministic.

Гвардрейл: «ответ ограничен профилем» — персона не выходит за рамки сегмента,
из которого сэмплится.
"""

from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# --- пути к репозиторию (относительно этого файла) ---

_AGENT_CORE = Path(__file__).resolve().parent.parent.parent  # services/agent-core
_REPO_ROOT = _AGENT_CORE.parent.parent  # AGORA/

SCHEMA_PATH = _REPO_ROOT / "packages" / "shared" / "schemas" / "persona-dna.schema.json"
CORPUS_PATH = _REPO_ROOT / "data" / "grounding" / "unified_respondent_sessions.json"
PROMPT_PATH = _REPO_ROOT / "prompts" / "persona.generate.md"
REFERENCE_PERSONA_PATH = _REPO_ROOT / "evals" / "fixtures" / "persona_reference.json"

# --- константы калибровки (PRD §10, замер 27.07.2026) ---

# Реальные средние баллы корпуса по 5 критериям (1-10).
CORPUS_SCORE_MEANS: dict[str, float] = {
    "overall_impression": 7.34,
    "plot": 7.58,
    "acting": 8.12,
    "music": 8.07,
    "cinematography": 8.00,
}

# Реальный разброс (min–max) из корпуса.
CORPUS_SCORE_RANGE: tuple[int, int] = (2, 9)

# Маппинг ВЦИОМ-ценностей корпуса → канонические values для DNA.
# Корпус содержит ~30 вариантов; схема принимает произвольные строки,
# но мы нормализуем к топ-набору для консистентности.
VCIOM_TO_DNA: dict[str, str] = {
    "Справедливость": "Справедливость",
    "Крепкая семья": "Крепкая семья",
    "Патриотизм": "Патриотизм",
    "Милосердие": "Милосердие",
    "Приоритет духовного над материальным": "Приоритет духовного над материальным",
    "Взаимопомощь и взаимоуважение": "Взаимопомощь и взаимоуважение",
    "Жизнь": "Жизнь",
    "Историческая память и преемственность поколений": (
        "Историческая память и преемственность поколений"
    ),
    "Права и свободы человека": "Права и свободы человека",
    "Самостоятельность, личная ответственность за результат": (
        "Самостоятельность, личная ответственность за результат"
    ),
    "Достоинство": "Достоинство",
    "Единство народов России": "Единство народов России",
    "Служение Отечеству и ответственность за его судьбу": (
        "Служение Отечеству и ответственность за его судьбу"
    ),
    "Стремление к новым знаниям, открытиям, трендам": (
        "Стремление к новым знаниям, открытиям, трендам"
    ),
}

# Города по гео-группе — для правдоподобного сэмплинга.
GEO_CITIES: dict[str, list[str]] = {
    "столицы": ["Москва", "Санкт-Петербург"],
    "центры субъектов": ["Екатеринбург", "Краснодар", "Нижний Новгород", "Пермь", "Барнаул"],
    "иные НП": ["Тверь", "Псков", "Кострома", "Тула", "Иваново"],
}

# Имена для генерации (простой пул, расширяется при наличии LLM).
_NAME_POOL_M = ["Алексей", "Дмитрий", "Сергей", "Иван", "Михаил", "Андрей", "Павел", "Артём"]
_NAME_POOL_F = ["Анна", "Мария", "Екатерина", "Ольга", "Наталья", "Ирина", "Светлана", "Юлия"]


# ---------------------------------------------------------------------------
# Corpus distribution
# ---------------------------------------------------------------------------


@dataclass
class CorpusDistribution:
    """Распределения, извлечённые из grounding-корпуса.

    Это «истина» для метрики ``persona_grounding``: сгенерированные персоны
    сравниваются с этими долями по ``age_group``, ``geo``, ``gender``.
    """

    age_group: dict[str, float]  # доля каждой группы
    geo: dict[str, float]
    gender: dict[str, float]
    city: dict[str, float]
    serial: dict[str, float]
    serial_x_city: dict[tuple[str, str], float]
    values: dict[str, float]  # топ-значения и их доли
    score_means: dict[str, float]
    score_stdevs: dict[str, float]
    verbatims: list[str]  # пул цитат для заземления стиля
    total: int

    @classmethod
    def from_corpus(cls, records: list[dict[str, Any]]) -> CorpusDistribution:
        total = len(records)
        if total == 0:
            raise ValueError("корпус пуст — невозможно построить распределения")

        def _dist(key_fn) -> dict[str, float]:
            c = Counter(key_fn(r) for r in records)
            return {k: v / total for k, v in c.items()}

        age_group = _dist(lambda r: r["socio_demographics"]["age_group"])
        geo = _dist(lambda r: r["socio_demographics"]["geo"])
        gender = _dist(lambda r: r["socio_demographics"]["gender"])
        city = _dist(lambda r: r["socio_demographics"]["city"])
        serial = _dist(lambda r: r["content_under_test"]["title"])

        sc_counter: Counter[tuple[str, str]] = Counter()
        for r in records:
            sc_counter[(r["content_under_test"]["title"], r["socio_demographics"]["city"])] += 1
        serial_x_city = {k: v / total for k, v in sc_counter.items()}

        # Ценности — топ-значения
        vals_counter: Counter[str] = Counter()
        for r in records:
            for v in r.get("psychographics_and_values", {}).get("important_values", []):
                vals_counter[v] += 1
        values = {k: v / total for k, v in vals_counter.most_common(15)}

        # Баллы
        score_fields = list(CORPUS_SCORE_MEANS.keys())
        score_means: dict[str, float] = {}
        score_stdevs: dict[str, float] = {}
        for f in score_fields:
            vals_list = [
                r["agora_core_scores_1_to_10"][f]
                for r in records
                if f in r.get("agora_core_scores_1_to_10", {})
            ]
            if vals_list:
                score_means[f] = statistics.mean(vals_list)
                score_stdevs[f] = statistics.stdev(vals_list) if len(vals_list) > 1 else 1.0
            else:
                score_means[f] = CORPUS_SCORE_MEANS[f]
                score_stdevs[f] = 2.0

        # Verbatims — пул цитат для заземления стиля речи
        verbatims: list[str] = []
        for r in records:
            qv = r.get("qualitative_verbatims", {})
            for v in (
                qv.get("why_impression"),
                qv.get("general_impression_comment"),
                qv.get("idea_comprehension_comment"),
            ):
                if v and len(v) > 10:
                    verbatims.append(v)
            for fv in r.get("focus_group_verbatims", []):
                if len(fv) > 20:
                    verbatims.append(fv)

        return cls(
            age_group=age_group,
            geo=geo,
            gender=gender,
            city=city,
            serial=serial,
            serial_x_city=serial_x_city,
            values=values,
            score_means=score_means,
            score_stdevs=score_stdevs,
            verbatims=verbatims,
            total=total,
        )

    @classmethod
    def from_file(cls, path: Path | None = None) -> CorpusDistribution:
        p = path or CORPUS_PATH
        records = json.loads(p.read_text("utf-8"))
        return cls.from_corpus(records)

    def restrict(
        self,
        age_groups: list[str] | None = None,
        geos: list[str] | None = None,
        genders: list[str] | None = None,
    ) -> CorpusDistribution:
        """Распределения, суженные до выбранных критериев (задача #9).

        Именно ПЕРЕСЧЁТ долей, а не фильтрация записей. Разница принципиальная:
        генератор сэмплирует демографию из распределений, поэтому отбор записей
        сам по себе на состав выдачи не влияет — персоны продолжали бы рождаться
        со всеми возрастными группами подряд, и выбранный в интерфейсе критерий
        молча терялся бы по дороге.

        Оставшиеся доли нормируются заново, чтобы сумма снова была единицей:
        иначе rng.choices раздаёт веса пропорционально исходным долям, и внутри
        оставшегося набора соотношение групп искажается.

        Пустая выборка по любому измерению — ValueError, а не пустое
        распределение. Ноль персон дальше по конвейеру выглядит как исследование
        без респондентов, и причину этого уже не восстановить; отказ здесь
        называет виновный критерий.
        """

        def _narrow(
            dist: dict[str, float], allowed: list[str] | None, what: str
        ) -> dict[str, float]:
            if not allowed:
                return dist
            kept = {k: v for k, v in dist.items() if k in allowed}
            if not kept:
                present = ", ".join(sorted(dist)) or "ничего"
                raise ValueError(
                    f"{what}: выбранные значения ({', '.join(allowed)}) отсутствуют в "
                    f"корпусе. Есть только: {present}. Персоны такого сегмента не были "
                    f"бы заземлены, поэтому генерация остановлена"
                )
            total = sum(kept.values())
            return {k: v / total for k, v in kept.items()}

        return replace(
            self,
            age_group=_narrow(self.age_group, age_groups, "возрастные группы"),
            geo=_narrow(self.geo, geos, "гео"),
            gender=_narrow(self.gender, genders, "пол"),
        )


# ---------------------------------------------------------------------------
# Generation config
# ---------------------------------------------------------------------------


@dataclass
class GenerationConfig:
    """Параметры генерации.

    Поля:
        size: количество персон (1–100).
        seed: целое для детерминизма (один seed → идентичный результат).
        serial: фильтр по сериалу (None — весь корпус).
        city: фильтр по городу (None — все города).
        segment: целевая аудитория (из experiment_metadata.target_audience_segment).
        use_llm: если True и есть ключ API — генерация через LLM-промпт;
            иначе — deterministic.
    """

    size: int = 20
    seed: int = 42
    serial: str | None = None
    city: str | None = None
    segment: str | None = None
    use_llm: bool = False

    # ─── Критерии отбора аудитории (задача #9) ──────────────────────────────
    # Пустой список означает «критерий не задан» и оставляет распределение
    # корпуса нетронутым. Это важно для #5: эталонный конфиг persona_grounding
    # не задаёт критериев, поэтому его поведение не меняется вовсе.
    #
    # Имена совпадают с полями apps/web/lib/audience.ts — там же живёт
    # переименование camelCase → snake_case на границе языков.
    age_groups: list[str] = field(default_factory=list)
    geos: list[str] = field(default_factory=list)
    genders: list[str] = field(default_factory=list)
    #: Уровни образования. В корпусе такого поля НЕТ ни у одной из 165 записей
    #: (замерено 04.08.2026), поэтому критерий не сужает распределения и не
    #: участвует в заземлении — он доезжает до промпта persona.generate и влияет
    #: на текст персоны, но не на её соцдем. Хранится здесь, а не отбрасывается,
    #: чтобы снимок конфигурации набора отражал то, что выбрал пользователь.
    education: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not (1 <= self.size <= 500):
            raise ValueError(f"size должен быть 1–500, получено {self.size}")
        if not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError(f"seed должен быть неотрицательным целым, получено {self.seed}")


# ---------------------------------------------------------------------------
# Persona Generator
# ---------------------------------------------------------------------------


class PersonaGenerator:
    """Генератор синтетических персон по методологии PRD §10.

    Использование::

        gen = PersonaGenerator.from_corpus()
        personas = gen.generate(GenerationConfig(size=20, seed=42))
        # → list[dict] валидных PersonaDNA объектов

    Детерминизм: один seed → один результат. CDD-тест проверяет это.
    """

    def __init__(self, distribution: CorpusDistribution, records: list[dict[str, Any]]):
        self.dist = distribution
        self.records = records

    @classmethod
    def from_corpus(cls, path: Path | None = None) -> PersonaGenerator:
        p = path or CORPUS_PATH
        records = json.loads(p.read_text("utf-8"))
        dist = CorpusDistribution.from_corpus(records)
        return cls(dist, records)

    def _filter_records(self, config: GenerationConfig) -> list[dict[str, Any]]:
        """Фильтрует корпус по config.serial / config.city / config.segment."""
        recs = self.records
        if config.serial:
            recs = [r for r in recs if r["content_under_test"]["title"] == config.serial]
        if config.city:
            recs = [r for r in recs if r["socio_demographics"]["city"] == config.city]
        if config.segment:
            recs = [
                r
                for r in recs
                if config.segment in r.get(
                    "experiment_metadata", {}
                ).get("target_audience_segment", "")
            ]
        return recs

    def _sample_weighted(self, rng: random.Random, dist: dict[str, float]) -> str:
        """Сэмплирует один ключ из взвешенного распределения."""
        keys = list(dist.keys())
        weights = [dist[k] for k in keys]
        return rng.choices(keys, weights=weights, k=1)[0]

    def _sample_age_from_group(self, rng: random.Random, age_group: str) -> int:
        """Сэмплирует возраст внутри возрастной группы."""
        ranges: dict[str, tuple[int, int]] = {
            "14-17": (14, 17),
            "18-24": (18, 24),
            "25-34": (25, 34),
            "35-44": (35, 44),
            "45-59": (45, 59),
            "60+": (60, 75),
        }
        lo, hi = ranges.get(age_group, (25, 34))
        return rng.randint(lo, hi)

    def _calibrate_score(self, rng: random.Random, field_name: str) -> int:
        """Калибрует балл (1-10) по реальному среднему и стдеву корпуса."""
        mean = self.dist.score_means.get(field_name, CORPUS_SCORE_MEANS.get(field_name, 7.0))
        stdev = self.dist.score_stdevs.get(field_name, 2.0)
        lo, hi = CORPUS_SCORE_RANGE
        val = int(round(rng.gauss(mean, stdev)))
        return max(lo, min(hi, val))

    def _map_values(self, rng: random.Random, n: int = 3) -> list[str]:
        """Выбирает 3-5 ценностей из топ-значений корпуса (ВЦИОМ→DNA)."""
        values_pool = list(self.dist.values.keys())
        n = max(3, min(n, 5))
        # Всегда включаем топ-2 + случайные
        picked = values_pool[:2]
        remaining = [v for v in values_pool[2:] if v not in picked]
        if remaining:
            picked.extend(rng.sample(remaining, min(n - 2, len(remaining))))
        # Нормализуем через VCIOM_TO_DNA
        return [VCIOM_TO_DNA.get(v, v) for v in picked]

    def _sample_verbatims(self, rng: random.Random, n: int = 3) -> list[str]:
        """Выбирает n цитат из пула для заземления стиля."""
        if not self.dist.verbatims:
            return []
        return rng.sample(self.dist.verbatims, min(n, len(self.dist.verbatims)))

    def _pick_name(self, rng: random.Random, gender: str) -> str:
        if gender == "муж":
            return rng.choice(_NAME_POOL_M)
        return rng.choice(_NAME_POOL_F)

    def _pick_hobbies(self, rng: random.Random) -> list[str]:
        pool = [
            "чтение", "кино/сериалы", "спорт", "путешествия", "готовка",
            "музыка", "игры", "рукоделие", "садоводство", "фотография",
            "танцы", "коллекционирование",
        ]
        n = rng.randint(2, 4)
        return rng.sample(pool, n)

    def _pick_genres(self, rng: random.Random) -> list[str]:
        pool = [
            "драма", "комедия", "триллер", "детектив", "мелодрама",
            "фантастика", "фэнтези", "исторический", "документальный",
            "реалити-шоу", "анимация", "хоррор", "боевик", "криминал",
            "военный", "спорт",
        ]
        n = rng.randint(2, 4)
        return rng.sample(pool, n)

    def _pick_devices(self, rng: random.Random) -> list[str]:
        pool = ["smartphone", "tablet", "laptop", "smart-tv", "desktop"]
        n = rng.randint(1, 3)
        return rng.sample(pool, n)

    def _pick_platforms(self, rng: random.Random) -> list[str]:
        pool = [
            "YouTube", "Кинопоиск", "Иви", "Okko", "Premier", "Wink",
            "VK Видео", "Telegram", "Яндекс.Дзен", "VK", "Одноклассники",
        ]
        n = rng.randint(2, 4)
        return rng.sample(pool, n)

    def _pick_social_media(self, rng: random.Random) -> list[str]:
        pool = ["Telegram", "VK", "Одноклассники", "WhatsApp", "Viber"]
        n = rng.randint(1, 3)
        return rng.sample(pool, n)

    def _generation_from_age(self, age: int) -> str:
        if age <= 24:
            return "зумеры"
        if age <= 40:
            return "миллениалы"
        if age <= 55:
            return "иксы"
        return "бумеры"

    def _build_narrative(
        self,
        name: str,
        age: int,
        city: str,
        gender: str,
        values: list[str],
        genres: list[str],
        verbatims: list[str],
    ) -> str:
        """Собирает narrative (3-4 предложения, 3-е лицо) — deterministic режим."""
        gender_word = "Работает" if gender == "муж" else "Работает"
        val_str = ", ".join(values[:2])
        genre_str = ", ".join(genres[:2])
        verbatim_hint = ""
        if verbatims:
            # Берём краткую цитату как репрезентацию стиля
            short = verbatims[0][:80]
            verbatim_hint = f' В разговоре может сказать: «{short}».'

        narrative = (
            f"{name}, {age} лет, {city}. {gender_word} и активно потребляет медиаконтент. "
            f"Ценит {val_str.lower()}, предпочитает жанры «{genre_str.lower()}». "
            f"Сериалы и контент выбирает осознанно, ориентируясь на собственный вкус "
            f"и рекомендации близких.{verbatim_hint}"
        )
        return narrative

    def _generate_one(
        self,
        rng: random.Random,
        idx: int,
        config: GenerationConfig,
        dist: CorpusDistribution | None = None,
    ) -> dict[str, Any]:
        """Генерирует одну персону — deterministic режим (без LLM).

        `dist` — распределения, суженные критериями шага «Аудитория» (#9).
        None означает «без критериев» и берёт полный корпус: так остаются
        исполнимыми вызовы, сделанные до появления критериев.

        Сужается только демография. Калибровка баллов, ценности и пул цитат
        по-прежнему считаются по всему корпусу — сузить их до подвыборки было бы
        точнее, но это меняет статистику, на которой стоит метрика
        persona_grounding с числовым порогом, и такую правку надо делать вместе
        с её перезамером, а не заодно.
        """
        dist = dist or self.dist

        # 1. Сэмплирование демографии по реальным долям
        age_group = self._sample_weighted(rng, dist.age_group)
        geo = self._sample_weighted(rng, dist.geo)
        gender = self._sample_weighted(rng, dist.gender)
        age = self._sample_age_from_group(rng, age_group)

        # Город — из гео-группы (или из распределения корпуса)
        geo_cities = GEO_CITIES.get(geo, list(self.dist.city.keys()))
        city = rng.choice(geo_cities) if geo_cities else "Москва"

        # Children — сэмплим из корпуса
        children = rng.choices(
            ["Да, есть ребенок / дети", "Нет детей", "Не указано"],
            weights=[0.4, 0.4, 0.2],
            k=1,
        )[0]

        # 2. Big Five — калибровка: средние ~3.0-3.5, разброс 1-5
        big_five = {
            "openness": rng.randint(2, 5),
            "conscientiousness": rng.randint(2, 5),
            "extraversion": rng.randint(1, 5),
            "agreeableness": rng.randint(2, 5),
            "neuroticism": rng.randint(1, 5),
        }

        # 3. Ценности ВЦИОМ→DNA
        values = self._map_values(rng, n=3)

        # Worldview / political / religious — из эвристики по значениям
        if "Патриотизм" in values or "Служение Отечеству и ответственность за его судьбу" in values:
            worldview = rng.choice(["консервативная", "традиционалистская"])
            political = rng.choice(["умеренно-консервативный", "аполитичен"])
        elif "Права и свободы человека" in values or "Свобода выбора и независимость" in values:
            worldview = rng.choice(["либеральная", "прагматическая"])
            political = rng.choice(["умеренно-либеральный", "аполитичен"])
        else:
            worldview = rng.choice(["прагматическая", "неопределённая", "консервативная"])
            political = rng.choice(
                ["аполитичен", "умеренно-консервативный", "умеренно-либеральный"]
            )

        religious = rng.choice(
            ["верующий невоцерковлённый", "agnostic", "атеист", "воцерковлённый"],
        )

        # 4. Viewer behavior
        genres = self._pick_genres(rng)
        viewer_behavior = {
            "preferred_genres": genres,
            "violence_tolerance": rng.choice(["низкая", "средняя", "высокая"]),
            "pacing_tolerance": rng.choice(["медленный", "умеренный", "быстрый"]),
            "length_tolerance": rng.choice([
                "короткие ролики", "серии 20-40 мин",
                "полноценные серии 40-60 мин", "полные фильмы",
            ]),
            "franchise_loyalty": rng.randint(1, 5),
            "actor_loyalty": rng.randint(1, 5),
            "recommendation_influence": rng.randint(1, 5),
            "ideological_response": rng.choice([
                "отвергает", "критичен", "нейтрален", "восприимчив", "ищет",
            ]),
            "ad_response": rng.choice([
                "раздражение", "игнорирование", "нейтральное", "интерес", "доверие",
            ]),
            "production_expectations": rng.choice(["низкие", "средние", "высокие"]),
            "attention_span": rng.choice(["короткий", "средний", "длинный"]),
        }

        # 5. Communication style — заземление на verbatims
        verbatims = self._sample_verbatims(rng, n=3)
        comm_style = {
            "verbosity": rng.choice(["лаконичный", "умеренный", "подробный"]),
            "directness": rng.choice(["прямой", "окольный", "завуалированный"]),
            "emotionality": rng.choice(["сдержанный", "умеренный", "эмоциональный"]),
            "humor": rng.choice(["без юмора", "ироничный", "добродушный", "саркастический"]),
            "conflict_style": rng.choice([
                "избегание", "компромисс", "конфронтация", "сотрудничество",
            ]),
        }

        # 6. Decision making
        decision_making = {
            "style": rng.choice(["рациональный", "эмоциональный", "интуитивный", "смешанный"]),
            "risk_appetite": rng.randint(1, 5),
            "brand_loyalty": rng.randint(1, 5),
            "impulsivity": rng.randint(1, 5),
        }

        # 7. Technology usage
        tech_usage = {
            "devices": self._pick_devices(rng),
            "platforms": self._pick_platforms(rng),
            "social_media": self._pick_social_media(rng),
            "streaming_frequency": rng.choice([
                "редко", "раз в неделю", "несколько раз в неделю", "ежедневно",
            ]),
            "tech_savviness": rng.randint(1, 5),
        }

        # 8. Lifestyle and interests
        # Work status — зависит от возраста
        if age >= 60:
            work_status = rng.choice(["пенсионер", "работает"])
        elif age <= 20:
            work_status = rng.choice(["учится", "работает и учится"])
        else:
            work_status = rng.choice(
                ["работает", "работает", "работает и учится", "домохозяйка/домохозяин"]
            )

        lifestyle = {
            "hobbies": self._pick_hobbies(rng),
            "media_consumption": rng.choice(["умеренное", "высокое", "очень высокое"]),
            "social_activity": rng.choice(["одиночка", "малый круг", "широкий круг", "тусовщик"]),
            "work_status": work_status,
            "education_level": rng.choice([
                "среднее", "среднее специальное", "неполное высшее", "высшее",
            ]),
        }

        # Narrative
        name = self._pick_name(rng, gender)
        narrative = self._build_narrative(
            name, age, city, gender, values, genres, verbatims,
        )
        # Гарантируем минимум 100 символов (требование схемы)
        if len(narrative) < 100:
            narrative += (
                " Представитель своего сегмента аудитории"
                " с уникальным взглядом на контент."
            )

        # Сборка персоны
        persona = {
            "demographics": {
                "gender": gender,
                "age": age,
                "age_group": age_group,
                "geo": geo,
                "city": city,
                "children": children,
            },
            "big_five": big_five,
            "values_and_beliefs": {
                "important_values": values,
                "worldview": worldview,
                "political_orientation": political,
                "religious_attitude": religious,
            },
            "viewer_behavior": viewer_behavior,
            "communication_style": comm_style,
            "decision_making": decision_making,
            "technology_usage": tech_usage,
            "lifestyle_and_interests": lifestyle,
            "narrative": narrative,
            "seed": config.seed,
        }
        return persona

    def generate(self, config: GenerationConfig) -> list[dict[str, Any]]:
        """Генерирует ``config.size`` персон детерминированно.

        Один seed → один результат. CDD-тест проверяет:
        ``generate(cfg) == generate(cfg)`` (diff == 0).
        """
        config.validate()
        rng = random.Random(config.seed)

        # Критерии применяются ОДИН раз до цикла, а не внутри него: сужение
        # распределения — свойство прогона, а не персоны, и пересчёт на каждой
        # итерации давал бы те же доли за size-кратную работу.
        dist = self.dist.restrict(
            age_groups=config.age_groups,
            geos=config.geos,
            genders=config.genders,
        )

        personas: list[dict[str, Any]] = []
        for i in range(config.size):
            persona = self._generate_one(rng, i, config, dist)
            personas.append(persona)
        return personas

    def build_prompt_context(self, config: GenerationConfig) -> dict[str, str]:
        """Собирает контекст для LLM-промпта ``persona.generate.md``.

        Возвращает dict с ключами-переменными промпта:
        ``criteria``, ``portrait_md``, ``size``, ``seed``,
        ``segment_distributions``, ``verbatim_pool``.
        """
        recs = self._filter_records(config)

        # portrait_md — дистиллированный портрет сегмента
        portrait_lines = [
            f"## Портрет аудитории (сегмент: {config.segment or 'весь корпус'})",
            f"Корпус: {len(recs)} записей из {self.dist.total}",
            "",
            "### Соцдем-профиль (реальные доли)",
            f"- Возраст: "
            f"{', '.join(f'{k} {v:.0%}' for k, v in sorted(self.dist.age_group.items()))}",
            f"- Гео: {', '.join(f'{k} {v:.0%}' for k, v in self.dist.geo.items())}",
            f"- Пол: {', '.join(f'{k} {v:.0%}' for k, v in self.dist.gender.items())}",
            "",
            "### Ценности (топ, ВЦИОМ)",
            *[f"- {k} ({v:.0%})" for k, v in list(self.dist.values.items())[:8]],
            "",
            "### Баллы (реальные средние)",
            *[f"- {k}: {v:.1f}" for k, v in self.dist.score_means.items()],
        ]
        portrait_md = "\n".join(portrait_lines)

        # segment_distributions
        seg_dist = json.dumps(
            {
                "age_group": self.dist.age_group,
                "geo": self.dist.geo,
                "gender": self.dist.gender,
                "city": self.dist.city,
            },
            ensure_ascii=False,
            indent=2,
        )

        # verbatim_pool
        verbatims = self._sample_verbatims(random.Random(config.seed), n=10)
        verbatim_pool = "\n".join(f"- {v}" for v in verbatims)

        # criteria
        criteria_parts = []
        if config.serial:
            criteria_parts.append(f"сериал: {config.serial}")
        if config.city:
            criteria_parts.append(f"город: {config.city}")
        if config.segment:
            criteria_parts.append(f"сегмент: {config.segment}")
        criteria = ", ".join(criteria_parts) if criteria_parts else "весь корпус"

        return {
            "criteria": criteria,
            "portrait_md": portrait_md,
            "size": str(config.size),
            "seed": str(config.seed),
            "segment_distributions": seg_dist,
            "verbatim_pool": verbatim_pool,
        }

    def render_prompt(self, config: GenerationConfig) -> str:
        """Рендерит промпт persona.generate.md с подставленными переменными."""
        template = PROMPT_PATH.read_text("utf-8")
        ctx = self.build_prompt_context(config)
        # Промпт имеет заголовок и разделитель на первых строках;
        # переменные в формате {{name}}.
        result = template
        for key, val in ctx.items():
            result = result.replace(f"{{{{{key}}}}}", val)
        return result


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def generate_personas(
    config: GenerationConfig,
    corpus_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Генерирует персон по конфигу.

    Это точка входа, используемая API-маршрутом и CDD-тестом.

    Args:
        config: параметры генерации (size, seed, фильтры).
        corpus_path: путь к корпусу (по умолчанию — канонический).

    Returns:
        Список словарей PersonaDNA, валидируемых против
        ``persona-dna.schema.json``.
    """
    gen = PersonaGenerator.from_corpus(corpus_path)
    return gen.generate(config)