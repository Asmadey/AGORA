"""
Расчёты Приложения 2 — по формулам заказчика и на его же примерах.

─── Почему тесты написаны на числах, а не на свойствах ──────────────────────
У этих формул есть внешний источник: заказчик прислал не только требования, но
и картинки-примеры с готовыми числами. Это единственная сверка, которая у нас
вообще есть, — всё остальное считается нашим же кодом по нашим же данным.

Так уже было с `persona_grounding`: он сверял маргиналы корпуса с генератором,
который из этого корпуса и сэмплирует, то есть обе стороны сравнения были одним
источником. Метрика выглядела метрикой качества и не могла ничего поймать.

─── Что именно проверяется ──────────────────────────────────────────────────
Каждый показатель Приложения 2 на выборке, где ответ известен заранее:

  в. 1–5   среднее, доля 8–10, интегральный индекс удовлетворённости
  в. 6     среднее, доля 8–10
  в. 7     доли по каждому из пятнадцати вариантов, счёт ОТВЕТОВ
  в. 8     доли по девятнадцати вариантам
  в. 9     доли по каждой подтеме, интегральный показатель восприятия
  в. 10–14 доли по вариантам
  в. 15    NPS = доля 9–10 минус доля 0–6, группы 9–10 / 7–8 / 0–6
  везде    то же самое в срезе «14-35» и числа n и base рядом

Отдельно проверяется порог: доли в срезе меньше двадцати персон не считаются, а
называются неподсчитанными. Доля по группе из пяти шагает по двадцать
процентных пунктов и на экране выглядит ровно так же, как доля по сотне.
"""
from __future__ import annotations

import json
import pathlib

from agent_core.analytics.survey_stats import survey_tally

REPO = pathlib.Path(__file__).resolve().parents[3]
SURVEY = json.loads((REPO / "data" / "survey" / "customer_2026.json").read_text("utf-8"))
QUESTIONS = SURVEY["questions"]


def persona(pid: str, age: int, gender: str = "жен", city: str = "Пермь") -> dict:
    return {
        "id": pid,
        "dna": {"demographics": {"age": age, "gender": gender, "city": city,
                                 "geo": "центры субъектов"}},
    }


def answer(pid: str, fields: dict) -> dict:
    return {"persona_id": pid, "replication": 0, "answer": {"survey_answers": dict(fields)}}


# ─── Шкалы ───────────────────────────────────────────────────────────────────


def test_среднее_и_доля_верхних_баллов():
    """Доля 8–10 — «топ-бокс» заказчика. Считается от охвата, не от ответивших."""
    answers = [answer(f"p{i}", {"q01-plot": v}) for i, v in enumerate([10, 9, 8, 7, 0])]
    personas = [persona(f"p{i}", 30) for i in range(5)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    plot = out["questions"]["q01-plot"]["total"]
    assert plot["n"] == 5
    assert plot["mean"] == 6.8
    assert plot["top_box"] == 0.6, "восьмёрка, девятка и десятка из пяти ответов"


def test_ноль_попадает_в_среднее_а_не_считается_пропуском():
    """
    Шкала заказчика 0–10, и ноль — настоящая оценка «совсем не понравился».
    Спутать его с «не ответил» значило бы завысить среднее на самых плохих
    материалах, то есть ровно там, где отчёт важнее всего.
    """
    answers = [answer("p0", {"q01-plot": 0}), answer("p1", {"q01-plot": 10})]
    personas = [persona("p0", 30), persona("p1", 30)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    plot = out["questions"]["q01-plot"]["total"]
    assert plot["n"] == 2
    assert plot["mean"] == 5.0


def test_интегральный_индекс_удовлетворённости_среднее_долей_по_пяти():
    """
    Формула заказчика: «среднее арифметическое доли тех, кто поставил от 8 до 10
    баллов по каждому параметру». Параметров пять — вопросы 1–5.
    """
    # Один ответ, где 8–10 стоит у трёх параметров из пяти: доли 1,1,1,0,0.
    answers = [answer("p0", {
        "q01-plot": 9, "q02-acting": 8, "q03-cinematography": 10,
        "q04-music": 5, "q05-overall": 4,
    })]
    out = survey_tally(QUESTIONS, answers, [persona("p0", 30)], min_segment=1)
    assert out["indices"]["satisfaction"]["total"] == 0.6


def test_индекс_не_считается_если_вопрос_не_задавали():
    """
    Среднее по четырём параметрам из пяти выглядит как среднее по пяти. Решение
    владельца: при неполном наборе индекс не считается вовсе.
    """
    subset = [q for q in QUESTIONS if q["number"] != 4]
    answers = [answer("p0", {"q01-plot": 9, "q02-acting": 9,
                             "q03-cinematography": 9, "q05-overall": 9})]
    out = survey_tally(subset, answers, [persona("p0", 30)], min_segment=1)
    assert out["indices"]["satisfaction"]["total"] is None


# ─── Закрытые вопросы ────────────────────────────────────────────────────────


def test_доли_по_вариантам_мультивыбора_считают_ответы():
    """
    Персона выбирает до трёх эмоций, значит сумма долей больше ста процентов.
    Знаменатель — размер охвата опрошенных персон, а не число выборов.
    """
    answers = [
        answer("p0", {"q07-emotions": "e-3, e-5"}),
        answer("p1", {"q07-emotions": "e-3"}),
    ]
    personas = [persona("p0", 30), persona("p1", 30)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    shares = out["questions"]["q07-emotions"]["total"]["shares"]
    assert shares["e-3"] == 1.0
    assert shares["e-5"] == 0.5
    assert shares["e-1"] == 0.0, "невыбранный вариант — ноль, а не отсутствие строки"


def test_служебный_вариант_остаётся_в_знаменателе():
    answers = [
        answer("p0", {"q07-emotions": "e-s1"}),
        answer("p1", {"q07-emotions": "e-3"}),
    ]
    personas = [persona("p0", 30), persona("p1", 30)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    shares = out["questions"]["q07-emotions"]["total"]["shares"]
    assert shares["e-s1"] == 0.5
    assert shares["e-3"] == 0.5


def test_доли_одиночного_выбора_суммируются_в_единицу():
    answers = [
        answer("p0", {"q10-importance": "i-1"}),
        answer("p1", {"q10-importance": "i-1"}),
        answer("p2", {"q10-importance": "i-2"}),
    ]
    personas = [persona(f"p{i}", 30) for i in range(3)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    shares = out["questions"]["q10-importance"]["total"]["shares"]
    assert round(sum(shares.values()), 6) == 1.0


# ─── Матрица и интегральный показатель восприятия ────────────────────────────


def test_доли_считаются_по_каждой_подтеме_отдельно():
    answers = [
        answer("p0", {"t1-1": "m-1", "t1-2": "m-2"}),
        answer("p1", {"t1-1": "m-1", "t1-2": "m-1"}),
    ]
    personas = [persona("p0", 30), persona("p1", 30)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    rows = out["questions"]["q09-themes"]["total"]["rows"]
    assert rows["t1-1"]["shares"]["m-1"] == 1.0
    assert rows["t1-2"]["shares"]["m-1"] == 0.5


def test_интегральный_показатель_восприятия_максимум_по_теме_потом_среднее():
    """
    Формула заказчика: «среднее арифметическое доли максимальных показателей
    "Скорее эта тема поднималась" по всем приоритетам, которые были заданы».
    Читается как: в каждой выбранной теме берём максимум по её подтемам, затем
    усредняем по темам.

    Здесь: в теме 1 максимум 1.0 (подтема t1-1), в теме 2 максимум 0.5.
    Среднее — 0.75.
    """
    answers = [
        answer("p0", {"t1-1": "m-1", "t1-2": "m-2", "t2-1": "m-1", "t2-2": "m-2"}),
        answer("p1", {"t1-1": "m-1", "t1-2": "m-2", "t2-1": "m-2", "t2-2": "m-2"}),
    ]
    personas = [persona("p0", 30), persona("p1", 30)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    assert out["indices"]["perception"]["total"] == 0.75


# ─── NPS ─────────────────────────────────────────────────────────────────────


def test_nps_девять_десять_минус_ноль_шесть():
    """Определение заказчика дословно: доля 9–10 минус доля 0–6."""
    scores = [10, 9, 8, 7, 6, 0]
    answers = [answer(f"p{i}", {"q15-recommend": v}) for i, v in enumerate(scores)]
    personas = [persona(f"p{i}", 30) for i in range(len(scores))]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    nps = out["indices"]["nps"]["total"]
    # промоутеры 2/6, детракторы 2/6 → 0
    assert nps == 0.0


def test_группы_рекомендации_девять_десять_семь_восемь_ноль_шесть():
    scores = [10, 9, 8, 7, 6, 0]
    answers = [answer(f"p{i}", {"q15-recommend": v}) for i, v in enumerate(scores)]
    personas = [persona(f"p{i}", 30) for i in range(len(scores))]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    groups = out["questions"]["q15-recommend"]["total"]["groups"]
    assert groups["9-10"] == 2 / 6
    assert groups["7-8"] == 2 / 6
    assert groups["0-6"] == 2 / 6


# ─── Срез 14–35 ──────────────────────────────────────────────────────────────


def test_срез_считается_по_точному_возрасту_а_не_по_группе():
    """
    Возрастные группы корпуса — 14-17, 18-24, 25-34, 35-44, … — и граница 35
    режет группу 35-44 пополам. Считать срез по группам значило бы либо потерять
    тридцатипятилетних, либо прихватить сорокалетних.
    """
    answers = [
        answer("p0", {"q01-plot": 10}),
        answer("p1", {"q01-plot": 0}),
        answer("p2", {"q01-plot": 10}),
    ]
    personas = [persona("p0", 35), persona("p1", 36), persona("p2", 14)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    target = out["questions"]["q01-plot"]["target"]
    assert target["n"] == 2, "тридцатипятилетний входит, тридцатишестилетний нет"
    assert target["mean"] == 10.0


def test_срез_меньше_порога_не_считается_а_называется():
    answers = [answer("p0", {"q01-plot": 10})]
    personas = [persona("p0", 20)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=20)
    target = out["questions"]["q01-plot"]["target"]
    assert target["mean"] is None
    assert target["n"] == 1
    assert target["below_threshold"] is True


def test_размер_среза_всегда_рядом_с_числом():
    answers = [answer(f"p{i}", {"q01-plot": 8}) for i in range(25)]
    personas = [persona(f"p{i}", 20) for i in range(25)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=20)
    for scope in ("total", "target"):
        assert out["questions"]["q01-plot"][scope]["n"] == 25


# ─── Состав аудитории ────────────────────────────────────────────────────────


def test_состав_аудитории_показывается_без_порога():
    """
    Разрез по городам заказчик требует прямо, а городов в корпусе семь: при
    сотне персон в каждом около четырнадцати. Порог, осмысленный для сравнения
    средних, здесь уничтожил бы само требование.
    """
    personas = [persona("p0", 30, city="Барнаул"), persona("p1", 40, city="Москва")]
    answers = [answer("p0", {}), answer("p1", {})]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=20)
    cities = out["audience"]["city"]
    assert cities == {"Барнаул": 1, "Москва": 1}
    assert out["audience"]["total"] == 2
    assert out["audience"]["target"] == 1, "в срез 14–35 попадает один"


# ─── Гейтинг QA ──────────────────────────────────────────────────────────────


def test_ответ_нарушивший_правило_не_идёт_в_расчёт():
    """
    Политика владельца 17.09.2026: судья информирует, правила гейтят. Ответ,
    помеченный ДЕТЕРМИНИРОВАННЫМ правилом (`source: "rule"`), из агрегата
    выбывает — балл вне шкалы в среднее не положишь.

    До этой проверки `survey_stats` считал по всем ответам подряд, хотя рядом,
    в `aggregate.py`, для этого уже жила `surviving()`. Расхождение было бы
    невидимым: два числа в одном отчёте, посчитанные по разным выборкам.
    """
    answers = [answer("p0", {"q01-plot": 10}), answer("p1", {"q01-plot": 0})]
    personas = [persona("p0", 30), persona("p1", 30)]
    flags = [{"persona_id": "p1", "replication": 0, "verdict": "regenerate", "source": "rule"}]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1, qa_flags=flags)
    plot = out["questions"]["q01-plot"]["total"]
    assert plot["n"] == 1
    assert plot["mean"] == 10.0


def test_вердикт_судьи_из_расчёта_не_выбрасывает():
    """
    `source: "judge"` информирует. Замер 17.09.2026: три четверти отбраковок
    судьи оказались дефектом правила, а не качеством ответа.
    """
    answers = [answer("p0", {"q01-plot": 10}), answer("p1", {"q01-plot": 0})]
    personas = [persona("p0", 30), persona("p1", 30)]
    flags = [{"persona_id": "p1", "replication": 0, "verdict": "regenerate", "source": "judge"}]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1, qa_flags=flags)
    assert out["questions"]["q01-plot"]["total"]["n"] == 2


def test_число_выбывших_названо_в_результате():
    """Читатель обязан знать, на скольких ответах стоит вывод."""
    answers = [answer("p0", {"q01-plot": 10}), answer("p1", {"q01-plot": 0})]
    personas = [persona("p0", 30), persona("p1", 30)]
    flags = [{"persona_id": "p1", "replication": 0, "verdict": "regenerate", "source": "rule"}]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1, qa_flags=flags)
    assert out["excluded_by_qa"] == 1


def test_рядом_с_числом_ответивших_стоит_число_опрошенных():
    """
    Заказчик подписывает доли «в % от опрошенных», поэтому знаменатель — размер
    охвата, а не число ответивших. При замеренных 40 % пропусков значения
    расходятся вдвое.

    Выбирать знаменатель за читателя нельзя, поэтому в результате стоят оба
    числа: `n` — сколько ответили на этот вопрос, `base` — сколько персон
    вообще опрашивали. Доля «в % от опрошенных» получается делением на `base`
    и используется непосредственно редьюсерами.
    """
    answers = [answer("p0", {"q01-plot": 10}), answer("p1", {})]
    personas = [persona("p0", 30), persona("p1", 30)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    plot = out["questions"]["q01-plot"]["total"]
    assert plot["n"] == 1, "ответил один"
    assert plot["base"] == 2, "опрашивали двоих"


def test_знаменатель_среза_это_размер_среза():
    answers = [answer(f"p{i}", {"q01-plot": 8}) for i in range(3)]
    personas = [persona("p0", 20), persona("p1", 25), persona("p2", 60)]
    out = survey_tally(QUESTIONS, answers, personas, min_segment=1)
    assert out["questions"]["q01-plot"]["total"]["base"] == 3
    assert out["questions"]["q01-plot"]["target"]["base"] == 2


# ─── Неразобранный ответ не голосует ─────────────────────────────────────────
#
# Персона, назвавшая два варианта там, где разрешён один, не выразила мнения —
# она нарушила форму. Прежде такой ответ попадал в подсчёт целиком: `errors`
# рос, но росли и оба счётчика, и обе доли выходили по 100 %.
#
# Это тот же класс промаха, что проглоченный вариант не из списка, только с
# обратным знаком: там голос терялся, здесь он удваивается. И выглядит это
# на графике как единодушие аудитории.


def test_ответ_с_ошибкой_формы_в_доли_не_идёт():
    question = {
        "id": "q", "type": "multi_choice", "maxChoices": 1,
        "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
    }
    answers = [answer("p0", {"q": "a, b"})]
    personas = [persona("p0", 30)]
    out = survey_tally([question], answers, personas, min_segment=1)
    stats = out["questions"]["q"]["total"]
    assert stats["errors"] == 1, "нарушение формы обязано остаться видимым"
    assert stats["n"] == 0, "ответивших нет: форма нарушена"
    assert stats["counts"] == {"a": 0, "b": 0}
    assert stats["base"] == 1, "опрашивали одного — знаменатель не меняется"


def test_исправный_ответ_рядом_с_битым_считается():
    question = {
        "id": "q", "type": "multi_choice", "maxChoices": 1,
        "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
    }
    answers = [answer("p0", {"q": "a, b"}), answer("p1", {"q": "a"})]
    personas = [persona("p0", 30), persona("p1", 30)]
    stats = survey_tally([question], answers, personas, min_segment=1)["questions"]["q"]["total"]
    assert stats["n"] == 1
    assert stats["counts"] == {"a": 1, "b": 0}
    assert stats["shares"]["a"] == 0.5, "доля считается от охвата, а не от ответивших"
