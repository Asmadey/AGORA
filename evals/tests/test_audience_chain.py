#!/usr/bin/env python3
"""
Регрессионный тест цепочки «Аудитория»: интерфейс → API → генератор → запуск.

Это не задача из графа. Это проверка на разрыв, который граф не ловит, потому
что каждое звено по отдельности исправно.

─── Что вскрылось ────────────────────────────────────────────────────────────
Задача #9 переписала POST /api/audience: маршрут перестал ходить в LLM напрямую
и начал звать заземлённый генератор из корпуса. Маршрут при этом получил новый
контракт тела — parseAudienceChoice ждёт {kind, criteria|personaSetId}.

Дальше выяснилось три вещи, и ни одну из них тест #9 увидеть не мог, потому что
он прогоняет генератор напрямую, минуя и маршрут, и интерфейс:

1. Шаг визарда AudienceStep.tsx не делает ни одного POST. Он читает заземление
   (GET /api/audience) и список наборов, а критерии складывает в черновик. Ветка
   «создать аудиторию» не доходит до генератора никогда.

2. Запуск (POST /api/tasks, задача #11) принимает только personaSetId. Набора
   при генерации по критериям не возникает — создавать его некому. То есть даже
   если бы шаг сходил в генератор, передать результат в запуск было бы нечем.

3. Старая страница /audience зовёт lib/ai.ts::generateAudience, а тот шлёт
   {size, context, options} — контракт, который parseAudienceChoice отвергает.
   Страница отвечает 400 на каждую попытку.

Итог: в графе #9 «сделана», её собственный тест зелёный, а пользователь не может
создать аудиторию по критериям ни из визарда, ни со страницы.

─── Про LLM ──────────────────────────────────────────────────────────────────
Отдельный пункт. PersonaGenerator.generate() — чистое сэмплирование по seed:
берёт доли из корпуса и раскладывает персон по ним. Функции build_prompt_context
и render_prompt собирают полный промпт persona.generate.md, но их не вызывает
никто. То есть промпт написан, переменные подставляются, а в модель не уходит
ничего.

Требование «идёт в LLM с заземлённым генератором» означает оба слова сразу, и
порядок здесь важен: заземление даёт факты, модель даёт язык. Обратный порядок —
модель придумывает факты, а корпус используется как вдохновение — это ровно то,
от чего #9 уходила.

Поэтому проверка требует не «есть вызов OpenAI», а три свойства сразу:
  · поля, по которым считается persona_grounding, модель НЕ переписывает;
  · без ключа генерация работает и даёт тот же результат (иначе CDD #5
    «diff == 0» становится непроверяемым нигде, кроме машины с ключом);
  · повторный вызов с тем же seed не платит второй раз — как в кэше #16.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core"
WEB = REPO / "apps" / "web"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    # Пояснение печатается только к упавшей проверке. К зелёной оно читается как
    # описание дефекта, которого нет, — и в выводе на 15 строк это сбивает
    # сильнее, чем помогает.
    shown = "" if ok else detail
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {shown}" if shown else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


def read(p: Path) -> str:
    return p.read_text("utf-8") if p.exists() else ""


def strip_comments(ts: str) -> str:
    """Убирает комментарии: искать вызовы надо в коде, а не в объяснениях к нему."""
    out, i, n = [], 0, len(ts)
    while i < n:
        if ts.startswith("/*", i):
            end = ts.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif ts.startswith("//", i):
            end = ts.find("\n", i)
            i = n if end == -1 else end
        else:
            out.append(ts[i])
            i += 1
    return "".join(out)


# ═══════════════════════════════════════════════════════════════════════════
# ЗВЕНО 1: шаг визарда доходит до генератора
# ═══════════════════════════════════════════════════════════════════════════

print("== Звено 1: интерфейс → API ==")

step_src = strip_comments(read(WEB / "components" / "agora" / "AudienceStep.tsx"))
check("шаг «Аудитория» существует", bool(step_src))

check(
    "шаг отправляет критерии в /api/audience, а не только читает заземление",
    'method: "POST"' in step_src or "method: 'POST'" in step_src,
    "в компоненте нет ни одного POST — ветка «создать аудиторию» никуда не ведёт"
    if step_src else "файла нет",
)

check(
    "отправка идёт именно на /api/audience",
    step_src.count("/api/audience") >= 2,
    f"вхождений /api/audience: {step_src.count('/api/audience')} "
    f"(нужны GET заземления и POST генерации)",
)

# Кнопка обязана уметь показать, что идёт генерация, и не давать нажать дважды:
# вызов генератора — это деньги, а не просто задержка.
check(
    "состояние генерации отражено в интерфейсе",
    any(k in step_src for k in ("isGenerating", "generating", "pending", "busy")),
    "нет флага занятости — двойное нажатие оплатит генерацию дважды",
)


# ═══════════════════════════════════════════════════════════════════════════
# ЗВЕНО 2: результат генерации можно передать в запуск
# ═══════════════════════════════════════════════════════════════════════════

print("== Звено 2: API → запуск ==")

route_src = strip_comments(read(WEB / "app" / "api" / "audience" / "route.ts"))
check("маршрут /api/audience существует", bool(route_src))

# Запуск (#11) принимает personaSetId. Значит генерация ОБЯЗАНА его создать,
# иначе результат генерации некуда деть: он вернётся в браузер и там умрёт.
check(
    "генерация сохраняет набор персон и возвращает его id",
    "personaSetId: null" not in route_src,
    "маршрут возвращает personaSetId: null — запуску (#11) нечего передать, "
    "сгенерированные персоны никуда не сохраняются"
    if "personaSetId: null" in route_src else "",
)

check(
    "генерация пишет персон в хранилище арендатора",
    any(k in route_src for k in ("insertPersonaSet", "createPersonaSet", "savePersonas")),
    "нет записи в БД — персоны существуют только в теле ответа",
)

launch_src = strip_comments(read(WEB / "app" / "api" / "tasks" / "route.ts"))
check(
    "запуск принимает набор персон",
    "personaSetId" in launch_src,
)


# ═══════════════════════════════════════════════════════════════════════════
# ЗВЕНО 3: старая страница /audience говорит на том же контракте
# ═══════════════════════════════════════════════════════════════════════════

print("== Звено 3: страница /audience ==")

ai_src = strip_comments(read(WEB / "lib" / "ai.ts"))
page_src = strip_comments(read(WEB / "app" / "audience" / "page.tsx"))
contract_src = read(WEB / "lib" / "audience.ts")

# parseAudienceChoice различает ветки по полю kind. Клиент, который его не шлёт,
# получит 400 — и это не гипотеза, а прямое следствие контракта.
posts_to_audience = "/api/audience" in ai_src
if not posts_to_audience:
    skip("контракт lib/ai.ts совпадает с контрактом маршрута",
         "lib/ai.ts больше не обращается к /api/audience")
else:
    # parseAudienceChoice читает критерии С ВЕРХНЕГО УРОВНЯ тела и различает
    # ветки по наличию personaSetId — поля-дискриминатора у него нет. Поэтому
    # проверяется словарь полей, а не наличие какого-то одного ключа.
    accepted = ("ageGroups", "geos", "genders", "size")
    missing = [k for k in accepted if k not in ai_src]
    check(
        "контракт lib/ai.ts совпадает с контрактом маршрута",
        not missing,
        f"generateAudience не шлёт поля {missing}, которых ждёт parseAudienceChoice "
        f"→ маршрут ответит 400",
    )
    # Вокабуляр прототипа: маршрут его не читает, а наличие в сигнатуре создаёт
    # впечатление, что эти входы на что-то влияют.
    dead = [k for k in ("context", "options") if f"{k}," in ai_src or f"{k}?" in ai_src]
    check(
        "мёртвые параметры прототипа убраны из generateAudience",
        not dead,
        f"остались параметры, которые маршрут игнорирует: {dead}",
    )

if not page_src:
    skip("страница /audience не обходит заземлённый генератор", "страницы нет")
else:
    # fetchNewsContext подмешивал в генерацию новостной контекст — то есть
    # источник, которого нет в корпусе. Для заземлённой генерации это лишний
    # вход: он влияет на персон, а persona_grounding о нём не знает.
    check(
        "страница /audience не подмешивает незаземлённый контекст",
        "fetchNewsContext" not in page_src,
        "новостной контекст едет в генерацию мимо корпуса",
    )


# ═══════════════════════════════════════════════════════════════════════════
# ЗВЕНО 4: генератор действительно ходит в модель
# ═══════════════════════════════════════════════════════════════════════════

print("== Звено 4: генератор → LLM ==")

gen_src = read(CORE / "agent_core" / "persona" / "generator.py")
check("генератор существует", bool(gen_src))

# Проверяется точка входа, которую зовёт маршрут, а не файл, где лежит вызов:
# где именно живёт обогащение — вопрос раскладки, а вот доходит ли генерация до
# модели — вопрос требования.
cli_src = read(CORE / "agent_core" / "persona" / "generate_cli.py")
check(
    "точка входа генератора подключает обогащение моделью",
    "enrich" in cli_src,
    "generate_cli не зовёт обогащение — промпт собирается в никуда",
)
check(
    "обогащение включается флагом, а не всегда",
    "use_llm" in cli_src,
    "нет способа отключить модель — эталонный прогон persona_grounding "
    "перестанет быть воспроизводимым",
)

enrich_src = read(CORE / "agent_core" / "persona" / "enrich.py")
check(
    "обогащение персон моделью выделено в отдельный модуль",
    bool(enrich_src),
    "нет agent_core/persona/enrich.py",
)

check(
    "обогащение кэшируется по содержимому, а не по id прогона",
    "cache_key" in enrich_src or "cache" in enrich_src.lower(),
    "без кэша повторный прогон (#30) платит за те же персоны заново",
)

check(
    "обогащение переживает отсутствие ключа",
    any(k in enrich_src for k in ("ConfigError", "fallback", "degrade", "skeleton")),
    "без ключа генерация обязана вернуть заземлённый скелет, а не упасть: "
    "иначе CDD #5 непроверяем нигде, кроме машины с ключом",
)


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ: заземление не деградирует от участия модели
# ═══════════════════════════════════════════════════════════════════════════

print("== Поведенческий уровень ==")

PROBE = r"""
import json, sys
sys.path.insert(0, %r)
from agent_core.persona.generator import GenerationConfig, PersonaGenerator

gen = PersonaGenerator.from_corpus()
cfg = GenerationConfig(size=8, seed=1234)
a = gen.generate(cfg)
b = gen.generate(cfg)
print(json.dumps({
    "same": a == b,
    "size": len(a),
    "keys": sorted(a[0].keys()) if a else [],
}, ensure_ascii=False))
""" % str(CORE)

proc = subprocess.run(
    [sys.executable, "-c", PROBE], capture_output=True, text=True, cwd=str(CORE), timeout=180
)
if proc.returncode != 0:
    check("генерация без ключа модели проходит и детерминирована", False,
          f"генератор упал: {proc.stderr.strip()[-200:]}")
else:
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        check("генерация без ключа модели проходит и детерминирована", False,
              f"неразбираемый вывод: {proc.stdout[-200:]}")
    else:
        check(
            "генерация без ключа модели проходит и детерминирована",
            data["same"] and data["size"] == 8,
            f"same={data['same']} size={data['size']}",
        )
        # Поля заземления обязаны остаться на месте: по ним считается
        # persona_grounding, и модель их не касается ни при каком исходе.
        grounded_fields = {"demographics", "seed"}
        present = set(data["keys"])
        check(
            "поля заземления присутствуют независимо от участия модели",
            grounded_fields <= present,
            f"нет полей: {sorted(grounded_fields - present)}" if not grounded_fields <= present
            else "",
        )


# ═══════════════════════════════════════════════════════════════════════════

print()
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)
n_ok = sum(1 for _, s, _ in results if s == PASS)
print(f"Итог: OK={n_ok} FAIL={n_fail} SKIP={n_skip}")
if n_fail:
    print("\nНевыполненные условия:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" — {detail}" if detail else ""))
sys.exit(1 if n_fail else 0)
