"""
Температура задаётся по стадиям и доезжает до каждого вызова модели.

─── Почему одного значения мало ─────────────────────────────────────────────
Стадии конвейера требуют противоположного. Персона обязана получиться непохожей
на соседнюю: это условие метрики `response_diversity`, и низкая температура
здесь даёт mode collapse — двадцать почти совпадающих портретов. Проверяющий и
аналитик обязаны быть повторяемыми: вердикт, меняющийся от прогона к прогону,
перестаёт быть свойством проверяемого.

До этой правки значения стояли числами прямо в клиентах — 0 в обогащении, 0.9 у
респондента, 0.3 в аналитике и портретах, 0.0 у судьи, — и поменять их можно
было только правкой кода с пересборкой образа.

─── Что здесь проверяется ───────────────────────────────────────────────────
Главное — СТЫК, а не арифметика. Настройка, которая выставляется в интерфейсе и
не применяется воркером, выглядит рабочей с обеих сторон: интерфейс её
сохраняет, воркер считает по своему умолчанию, и увидеть расхождение можно
только по счёту от провайдера и по доле отбраковок.

Поэтому проверяются три вещи:

1. Имена стадий в `lib/settings.ts` и в `TemperatureConfig` совпадают. Разойдясь
   на одну букву, они дадут ровно описанный выше немой отказ.
2. Умолчания совпадают по значениям. Два умолчания в разных местах однажды
   разъедутся, и никто не поймёт, какое действовало.
3. Снимок задачи доезжает до конфигурации, а отсутствующая стадия берёт
   умолчание, а не ноль: ноль здесь не «пусто», а «полная детерминированность».
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent_core.config import TemperatureConfig

REPO = Path(__file__).resolve().parents[3]
SETTINGS_TS = REPO / "apps" / "web" / "lib" / "settings.ts"


def ts_stages() -> dict[str, float]:
    """Стадии и умолчания из контракта интерфейса."""
    source = SETTINGS_TS.read_text("utf-8")
    block = source.split("TEMPERATURE_STAGES", 1)[1].split("] as const", 1)[0]
    return {
        key: float(default)
        for key, default in re.findall(
            r'key:\s*"([a-zA-Z]+)".*?default:\s*([0-9.]+)', block, re.S
        )
    }


def test_stage_names_match_the_web_contract():
    """Имена стадий совпадают с `lib/settings.ts`."""
    assert ts_stages(), "не удалось разобрать TEMPERATURE_STAGES — контракт не читается"
    assert set(ts_stages()) == set(TemperatureConfig.STAGES), (
        "состав стадий разошёлся: настройка, которую выставляют в интерфейсе, "
        "не применится воркером, и обе стороны будут выглядеть исправными"
    )


def test_defaults_match_the_web_contract():
    """Умолчания совпадают по значениям, а не только по именам."""
    defaults = TemperatureConfig.defaults()
    for stage, value in ts_stages().items():
        assert getattr(defaults, stage) == pytest.approx(value), (
            f"умолчание стадии {stage}: интерфейс обещает {value}, "
            f"воркер берёт {getattr(defaults, stage)}"
        )


def test_snapshot_wins_over_defaults():
    """Значения из снимка задачи применяются."""
    config = TemperatureConfig.for_task(
        {"temperatures": {"responseSimulation": 0.55, "answerJudge": 0.2}}
    )
    assert config.responseSimulation == pytest.approx(0.55)
    assert config.answerJudge == pytest.approx(0.2)


def test_missing_stage_falls_back_to_default_not_zero():
    """
    Пропущенная стадия берёт умолчание, а не ноль.

    Ноль здесь не «значение отсутствует», а «полная детерминированность»: на
    создании персон он означал бы mode collapse — двадцать одинаковых портретов
    вместо аудитории.
    """
    config = TemperatureConfig.for_task({"temperatures": {"answerJudge": 0.2}})
    assert config.personaCreation == pytest.approx(0.9)


def test_empty_snapshot_is_all_defaults():
    """Прогоны, начатые до появления раздела, идут на умолчаниях, а не падают."""
    assert TemperatureConfig.for_task({}) == TemperatureConfig.defaults()
    assert TemperatureConfig.for_task(None) == TemperatureConfig.defaults()


def test_out_of_range_value_is_rejected():
    """
    Значение вне 0..2 отвергается здесь, а не провайдером.

    Провайдер откажет посреди оплаченного прогона — после расшифровки и разбора
    кадров, — и отказ будет выглядеть сбоем сети, а не опечаткой в настройках.
    """
    with pytest.raises(ValueError, match="responseSimulation"):
        TemperatureConfig.for_task({"temperatures": {"responseSimulation": 7}})


# ─── Стык с клиентами ────────────────────────────────────────────────────────


def test_every_stage_has_a_caller():
    """
    У каждой стадии есть вызывающий.

    Стадия без вызывающего — ручка в интерфейсе, которая ничего не крутит.
    Проверяется по исходникам: имена стадий обязаны встречаться там, где
    собираются клиенты модели.
    """
    core = REPO / "services" / "agent-core" / "agent_core"
    # config.py исключён намеренно: там стадии ОБЪЯВЛЕНЫ — полем и элементом
    # STAGES, — и, считая его, проверка проходила бы на пустом месте. Ровно так
    # она и прошла в первый раз, ничего не проверив.
    sources = "\n".join(
        path.read_text("utf-8")
        for path in core.rglob("*.py")
        if path.name != "config.py"
    )
    for stage in TemperatureConfig.STAGES:
        assert stage in sources, (
            f"стадия {stage} нигде не читается: настройка есть, применения нет — "
            f"ручка в интерфейсе, которая ничего не крутит"
        )
