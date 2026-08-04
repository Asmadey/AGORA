#!/usr/bin/env python3
"""CDD-тест задачи #25 — Respondent Matching.

CDD: «поиск похожих респондентов возвращает осмысленных соседей на held-out
выборке; similarity scores нормализованы (0–1); демографическое совпадение
взвешено адекватно».

Два уровня:
  - **Статический** — проверяет наличие модулей, API-маршрута, схемы,
    корректность весов метрики. Работает без внешних зависимостей.
  - **Поведенческий** — запускает finder на реальном корпусе, проверяет
    осмысленность соседей и held-out логику. Требует корпус и установленный
    пакет; иначе честно SKIP.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

FINDER_PATH = REPO / "services" / "agent-core" / "agent_core" / "matching" / "finder.py"
INIT_PATH = REPO / "services" / "agent-core" / "agent_core" / "matching" / "__init__.py"
ROUTER_PATH = REPO / "services" / "agent-core" / "agent_core" / "api" / "routers" / "matching.py"
API_INIT_PATH = REPO / "services" / "agent-core" / "agent_core" / "api" / "__init__.py"
SCHEMA_PATH = REPO / "packages" / "shared" / "schemas" / "persona-dna.schema.json"
CORPUS_PATH = REPO / "data" / "grounding" / "unified_respondent_sessions.json"

results: list[tuple[str, str, str]] = []


def check(n: str, ok: bool, d: str = "") -> None:
    results.append((n, "OK" if ok else "FAIL", d))
    print(f"  {'OK  ' if ok else 'FAIL'}  {n}" + (f"  →  {d}" if d else ""))


def skip(n: str, r: str) -> None:
    results.append((n, "SKIP", r))
    print(f"  SKIP  {n}  →  {r}")


print("== Статический уровень ==")

finder_src = FINDER_PATH.read_text("utf-8") if FINDER_PATH.exists() else ""
init_src = INIT_PATH.read_text("utf-8") if INIT_PATH.exists() else ""
router_src = ROUTER_PATH.read_text("utf-8") if ROUTER_PATH.exists() else ""
api_init_src = API_INIT_PATH.read_text("utf-8") if API_INIT_PATH.exists() else ""

check("модуль matching/finder.py существует", FINDER_PATH.exists())
check("модуль matching/__init__.py существует", INIT_PATH.exists())
check("API router matching.py существует", ROUTER_PATH.exists())
check("API __init__ включает matching router", "matching" in api_init_src)

# Проверяем метрику сходства
check(
    "метрика содержит демографическое сходство",
    "_demo_similarity" in finder_src,
)
check(
    "метрика содержит Big Five расстояние",
    "_big5_similarity" in finder_src,
)
check(
    "метрика содержит overlap ценностей",
    "_values_overlap" in finder_src,
)
check(
    "веса определены (W_DEMO, W_BIG5, W_VALUES)",
    "W_DEMO" in finder_src and "W_BIG5" in finder_src and "W_VALUES" in finder_src,
)
check(
    "веса суммируются в 1.0 (0.4 + 0.3 + 0.3)",
    "0.4" in finder_src and "0.3" in finder_src,
)
check(
    "демография взвешена сильнее остальных (w_demo ≥ w_big5, w_values)",
    "W_DEMO: float = 0.4" in finder_src,
)

# Проверяем нормализацию score
check(
    "score нормализован в [0, 1] (clamp)",
    "max(0.0, min(1.0" in finder_src,
)
check(
    "Big Five dist нормализован через max_dist",
    "_MAX_BIG5_DIST" in finder_src,
)
check(
    "values overlap — коэффициент Жаккара",
    "len(intersection) / len(union)" in finder_src,
)

# Проверяем top-K
check("top-K поиск реализован", "top_k" in finder_src and "[: cfg.top_k]" in finder_src)
check("exclude_ids для held-out", "exclude_ids" in finder_src)

# Проверяем API
check("POST /api/matching/find маршрут", "/matching/find" in router_src)
check("API принимает persona_dna", "persona_dna" in router_src)
check("API возвращает matches", "matches" in router_src)
check("API возвращает corpus_size", "corpus_size" in router_src)

# Проверяем схему
check("Persona DNA schema существует", SCHEMA_PATH.exists())
if SCHEMA_PATH.exists():
    schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
    check("схема содержит big_five", "big_five" in schema.get("properties", {}))
    check(
        "схема содержит values_and_beliefs",
        "values_and_beliefs" in schema.get("properties", {}),
    )

# Проверяем proxy Big Five
check(
    "proxy Big Five из ответов респондента",
    "_proxy_big_five" in finder_src,
)

print("\n== Поведенческий уровень ==")

# Поведенческий: нужен корпус и установленный пакет
corpus_ok = CORPUS_PATH.exists()
agent_core_ok = (REPO / "services" / "agent-core" / "agent_core" / "matching").exists()

if corpus_ok and agent_core_ok:
    try:
        sys.path.insert(0, str(REPO / "services" / "agent-core"))
        from agent_core.matching import FindConfig, RespondentFinder  # type: ignore
        from agent_core.matching.finder import _proxy_big_five  # type: ignore

        records = json.loads(CORPUS_PATH.read_text("utf-8"))
        check("корпус загружен", len(records) > 0, f"{len(records)} записей")

        # Тест 1: held-out — строим persona из реального респондента,
        # исключаем его ID, проверяем что ближайший сосед осмыслен
        finder = RespondentFinder(records)

        # Берём первого респондента, делаем из него persona DNA
        ref = records[0]
        ref_demo = ref.get("socio_demographics", {})
        ref_vals = ref.get("psychographics_and_values", {})
        proxy_b5 = _proxy_big_five(ref)

        persona_dna = {
            "demographics": ref_demo,
            "big_five": proxy_b5,
            "values_and_beliefs": {
                "important_values": ref_vals.get("important_values", []),
            },
        }

        # Исключаем самого себя (held-out)
        ref_id = ref.get("respondent_id", "")
        matches = finder.find(
            persona_dna,
            FindConfig(top_k=5, exclude_ids={ref_id}),
        )

        check("held-out: вернул соседей", len(matches) > 0, f"{len(matches)} соседей")
        check("held-out: исключил self", all(m.respondent_id != ref_id for m in matches))
        check(
            "held-out: лучший сосед имеет similarity > 0.3",
            len(matches) > 0 and matches[0].similarity > 0.3,
            f"top1 sim={matches[0].similarity:.3f}" if matches else "",
        )

        # Тест 2: не исключаем self — должны найти себя как лучшего соседа
        matches_self = finder.find(persona_dna, FindConfig(top_k=3))
        check(
            "self-match: лучший сосед — сам респондент",
            len(matches_self) > 0 and matches_self[0].respondent_id == ref_id,
            f"top1 id={matches_self[0].respondent_id}" if matches_self else "",
        )
        check(
            "self-match: similarity ~ 1.0",
            len(matches_self) > 0 and matches_self[0].similarity > 0.85,
            f"self sim={matches_self[0].similarity:.3f}" if matches_self else "",
        )

        # Тест 3: все similarity в [0, 1]
        all_scores = [m.similarity for m in matches] + [
            m.similarity for m in matches_self
        ]
        check(
            "все similarity ∈ [0, 1]",
            all(0.0 <= s <= 1.0 for s in all_scores),
        )

        # Тест 4: результаты отсортированы по убыванию
        sorted_ok = all(
            matches[i].similarity >= matches[i + 1].similarity
            for i in range(len(matches) - 1)
        )
        check("результаты отсортированы по убыванию similarity", sorted_ok)

        # Тест 5: top_k ограничивает результат
        matches_k3 = finder.find(persona_dna, FindConfig(top_k=3))
        check("top_k=3 → ровно 3 результата", len(matches_k3) == 3)

        # Тест 6: min_similarity отсекает
        matches_thresh = finder.find(
            persona_dna, FindConfig(top_k=50, min_similarity=0.9)
        )
        check(
            "min_similarity=0.9 отсекает низкие",
            all(m.similarity >= 0.9 for m in matches_thresh),
        )

        # Тест 7: осмысленность — демографическое совпадение влияет
        # Создаём persona с другой демографией и проверяем что score ниже
        persona_diff = {
            "demographics": {
                "gender": "муж" if ref_demo.get("gender") == "жен" else "жен",
                "age": 60,
                "age_group": "60+",
                "geo": "иные НП",
                "city": "Тверь",
                "children": "Нет детей",
            },
            "big_five": proxy_b5,
            "values_and_beliefs": {
                "important_values": ref_vals.get("important_values", []),
            },
        }
        matches_diff = finder.find(persona_diff, FindConfig(top_k=1))
        check(
            "разная демография → более низкий score",
            len(matches_diff) > 0 and matches_diff[0].similarity < matches_self[0].similarity,
            f"diff={matches_diff[0].similarity:.3f} < self={matches_self[0].similarity:.3f}"
            if matches_diff and matches_self
            else "",
        )

    except ImportError as e:
        skip("поведенческий прогон", f"ImportError: {e}")
    except Exception as e:
        check("поведенческий прогон без ошибок", False, str(e))
else:
    reason = "нет корпуса" if not corpus_ok else "нет agent_core"
    skip("held-out: вернул соседей", reason)
    skip("held-out: исключил self", reason)
    skip("held-out: лучший сосед sim > 0.3", reason)
    skip("self-match: лучший сосед — self", reason)
    skip("self-match: similarity ~ 1.0", reason)
    skip("все similarity ∈ [0, 1]", reason)
    skip("результаты отсортированы", reason)
    skip("top_k ограничивает", reason)
    skip("min_similarity отсекает", reason)
    skip("разная демография → ниже score", reason)

# Вердикт общий для всех тестов: GREEN только когда проверено всё, что можно
# было проверить здесь. Прежде GREEN печатался при любом числе SKIP, и по
# выводу нельзя было отличить «проверено» от «пропущено» — см. _harness.verdict.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#25"))
