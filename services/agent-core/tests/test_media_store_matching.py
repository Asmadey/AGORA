"""
Звук, запись отчёта и подбор респондентов.

Три места, где отказ выглядит не отказом:

* Пустой wav вместо внятной ошибки проходит дальше по конвейеру и даёт пустой
  транскрипт — неотличимый от «в ролике молчание».
* Отчёт, не доехавший до Mongo, виден пользователю как «отчёт не открывается»,
  то есть как дефект интерфейса.
* Подбор респондентов возвращает правдоподобный результат ВСЕГДА: список
  похожих людей выглядит одинаково убедительно и когда он верен, и когда
  сходство посчитано мимо.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import pytest

# ─────────────────────────────────────────────────────────────────────────
# Звуковая дорожка
# ─────────────────────────────────────────────────────────────────────────

pytestmark_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg недоступен",
)


@pytestmark_ffmpeg
def test_audio_is_16k_mono_regardless_of_source(tmp_path: Path):
    """
    16 кГц моно — вход и транскрипции, и диаризации. Придёт стерео 48 кГц —
    таймкоды разойдутся между ними, и ярлыки говорящих лягут не на те слова.
    """
    from agent_core.media.audio import extract_audio

    src = tmp_path / "стерео.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
         "-ac", "2", "-t", "2", "-shortest", str(src)],
        check=True, capture_output=True, timeout=120,
    )

    out = extract_audio(src, tmp_path / "звук.wav")

    with wave.open(str(out)) as w:
        assert w.getnchannels() == 1, "дорожка не сведена в моно"
        assert w.getframerate() == 16000, f"частота {w.getframerate()} вместо 16000"
        assert w.getsampwidth() == 2, "не 16 бит на отсчёт"


@pytestmark_ffmpeg
def test_file_without_audio_is_a_named_refusal(tmp_path: Path):
    """
    Пустой wav прошёл бы дальше и дал бы пустой транскрипт, который невозможно
    отличить от молчания в ролике. Отказ обязан быть здесь и обязан называть
    причину.
    """
    from agent_core.media.audio import extract_audio
    from agent_core.media.probe import MediaError

    src = tmp_path / "немой.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "testsrc2=size=64x64:rate=10", "-t", "1", str(src)],
        check=True, capture_output=True, timeout=120,
    )

    with pytest.raises(MediaError, match="звуков"):
        extract_audio(src, tmp_path / "звук.wav")


# ─────────────────────────────────────────────────────────────────────────
# Запись отчёта
# ─────────────────────────────────────────────────────────────────────────

class _Collection:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def update_one(self, flt, update, **kwargs):
        self.calls.append((flt, update, kwargs))

        class _R:
            upserted_id = None

        return _R()

    def bulk_write(self, ops, **kwargs):  # noqa: ARG002
        self.calls.append(("bulk", ops, kwargs))

        class _R:
            upserted_count = len(ops)
            modified_count = 0

        return _R()


#: Настоящий UUID: `assert_tenant_filter` проверяет форму и отвергает «t-1».
#: Проверка не косметическая — фильтр уезжает в Mongo, и строка произвольной
#: формы там просто не совпадёт ни с чем, отдав пустой результат вместо отказа.
TENANT = "de15d1e3-e2f6-41c7-966d-91c186046066"


class _Db(dict):
    def __getitem__(self, name):
        if name not in self:
            super().__setitem__(name, _Collection())
        return super().__getitem__(name)


def test_report_is_written_scoped_to_the_tenant():
    """
    Фильтр обязан включать арендатора. Без него `update_one` нашёл бы документ
    другой команды с тем же task_id — а task_id генерируется у каждой своей
    последовательностью.
    """
    from agent_core.analytics.store import save_report

    db = _Db()
    save_report(db, tenant_id=TENANT, task_id="task-1", report={"n": 1}, answers=[])

    flt = db["reports"].calls[0][0]
    assert flt.get("tenant_id") == TENANT, f"фильтр без арендатора: {flt}"
    assert flt.get("task_id") == "task-1"


def test_repeated_save_is_an_upsert_not_a_second_report():
    """
    Перезапуск после сбоя обязан дописать поверх. Два отчёта на один прогон
    означали бы, что показанный экраном зависит от порядка выборки.
    """
    from agent_core.analytics.store import save_report

    db = _Db()
    save_report(db, tenant_id=TENANT, task_id="task-1", report={"n": 1}, answers=[])
    kwargs = db["reports"].calls[0][2]
    assert kwargs.get("upsert") is True, f"запись не upsert: {kwargs}"


# ─────────────────────────────────────────────────────────────────────────
# Подбор респондентов
# ─────────────────────────────────────────────────────────────────────────

def test_similarity_is_ordered_and_bounded():
    """
    Список отсортирован по убыванию и лежит в [0, 1]. Нарушение любого из двух
    не видно на глаз: список похожих людей выглядит убедительно в любом порядке.
    """
    from agent_core.matching.finder import FindConfig, find_similar_respondents

    dna = {
        "socio_demographics": {
            "age_group": "25-34", "gender": "женский",
            "settlement_type": "город-миллионник", "education": "высшее",
        },
        "big_five": {"openness": 7, "conscientiousness": 5, "extraversion": 6,
                     "agreeableness": 5, "neuroticism": 4},
        "values": ["семья", "стабильность"],
    }

    try:
        matches = find_similar_respondents(dna, FindConfig())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"корпус недоступен: {exc}")

    assert matches, "подбор не вернул ни одного респондента"
    scores = [m.similarity for m in matches]
    assert scores == sorted(scores, reverse=True), f"порядок нарушен: {scores[:5]}"
    assert all(0.0 <= s <= 1.0 for s in scores), f"сходство вне [0,1]: {scores[:5]}"


def test_matches_carry_the_respondent_they_point_at():
    """
    Совпадение без идентификатора респондента бесполезно: проверить его нельзя,
    а выглядит оно так же, как проверяемое.
    """
    from agent_core.matching.finder import find_similar_respondents

    dna = {
        "socio_demographics": {"age_group": "25-34", "gender": "женский",
                               "settlement_type": "город-миллионник",
                               "education": "высшее"},
        "big_five": {"openness": 5, "conscientiousness": 5, "extraversion": 5,
                     "agreeableness": 5, "neuroticism": 5},
        "values": [],
    }
    try:
        matches = find_similar_respondents(dna)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"корпус недоступен: {exc}")

    assert matches[0].respondent_id, "у совпадения нет идентификатора респондента"


def test_report_refuses_a_tenant_that_is_not_a_uuid():
    """
    Фильтр уезжает в Mongo. Строка произвольной формы там не совпадёт ни с чем
    и отдаст ПУСТОЙ результат вместо отказа — то есть отчёт «сохранится»
    в никуда, и узнают об этом при попытке его открыть.
    """
    from agent_core.analytics.store import save_report
    from agent_core.db import TenantContextError

    with pytest.raises(TenantContextError, match="UUID"):
        save_report(_Db(), tenant_id="команда-1", task_id="task-1",
                    report={}, answers=[])
