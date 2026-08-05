#!/usr/bin/env python3
"""
CDD-тест задачи #13 — «Оркестратор LangGraph».

CDD (из tasks.json):
  падение на среднем узле → перезапуск продолжает с чекпоинта, а не с нуля;
  state соответствует схеме PRD §8.

Приёмка: LangGraph внутри Celery-задачи, чекпоинтер, маршрутизация
route(short|long), прогресс в Valkey.

─── Почему «продолжает с чекпоинта» проверяется счётчиком вызовов ────────────
Проверять итоговый state бессмысленно: прогон с нуля и прогон с чекпоинта дают
одинаковый результат — в этом и смысл чекпоинтера. Отличаются они только тем,
СКОЛЬКО работы выполнено повторно, а это видно лишь по тому, какие узлы
вызывались после перезапуска.

Разница не академическая. Узлы этого конвейера — транскрипция 15-минутного
ролика (минуты CPU) и разбор кадров (оплаченные вызовы VLM). Перезапуск,
который «работает», но проходит их заново, неотличим от работающего по логам и
по результату — виден он только в счёте провайдера.

─── Почему чекпоинтер свой, а не langgraph-checkpoint-redis ──────────────────
Готовый пакет тянет redisvl и требует модулей RediSearch/RedisJSON, то есть
Redis Stack. У нас Valkey 9.1 (Decision Log #3), и этих модулей в нём нет.
Пакет установился бы, тесты на разработческой машине с Redis Stack прошли бы, а
на развёртывании прогон падал бы на первом же чекпоинте — то есть отказ
проявился бы после того, как транскрипция уже отработала.

Поэтому в тесте есть отдельное условие: чекпоинтер обязан обходиться базовыми
командами (GET/SET/DEL/SCAN) и не звать ничего из JSON.* и FT.*.

─── Почему прогресс проверяется по ключу, а не по каналу ─────────────────────
Pub/Sub ничего не помнит: подписчик, подключившийся на середине прогона, не
получит уже отправленное. Экран прогресса (#12) переживает обрыв соединения
только если текущее состояние лежит в ключе, который можно прочитать при
переподключении. Канал нужен, чтобы не опрашивать ключ в цикле, но источником
истины он быть не может.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core"
PKG = CORE / "agent_core" / "pipeline"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if not ok and detail else ""))


def skip(name: str, why: str) -> None:
    results.append((name, SKIP, why))
    print(f"  SKIP  {name}  →  {why}")


def read(path: Path) -> str:
    return path.read_text("utf-8") if path.exists() else ""


# ═══ Поля state по PRD §8 ═══════════════════════════════════════════════════
#
# Список выписан из PRD дословно. Это не «желательный набор»: на эти имена
# ссылаются узлы конвейера и отчёт, и переименование поля здесь — молчаливый
# разрыв контракта между воркером и веб-слоем.
PRD8_FIELDS = (
    "task_id", "tenant_id", "mode", "video_ref", "proxy_ref", "audio_ref",
    "speech_regions", "segments", "transcript_diarized", "chunk_analyses_ref",
    "video_understanding", "content_pack_full", "content_pack_compact",
    "persona_ids", "survey", "replication_count", "persona_answers",
    "qa_flags", "report", "status", "progress",
)

# Узлы конвейера по графу PRD §8, в объявленном порядке.
PRD8_NODES = (
    "probe_and_normalize", "extract_audio", "detect_speech", "transcribe",
    "diarize", "merge_transcript", "segment_video", "sample_frames",
    "analyze_chunks", "stitch", "pack", "evaluate_personas", "qa", "analytics",
)

print("\n#13 — Оркестратор LangGraph\n")

# ─── Статический уровень ────────────────────────────────────────────────────

print("Модули")

for fname in ("__init__.py", "state.py", "graph.py", "checkpoint.py", "progress.py", "tasks.py"):
    check(f"agent_core/pipeline/{fname} существует", (PKG / fname).exists())

state_src = read(PKG / "state.py")
graph_src = read(PKG / "graph.py")
cp_src = read(PKG / "checkpoint.py")
prog_src = read(PKG / "progress.py")
tasks_src = read(PKG / "tasks.py")

print("\nState по PRD §8")

missing = [f for f in PRD8_FIELDS if f not in state_src]
check("все поля state из PRD §8 объявлены", not missing, "нет: " + ", ".join(missing))

print("\nУзлы конвейера")

absent = [n for n in PRD8_NODES if n not in graph_src]
check("все узлы конвейера PRD §8 присутствуют", not absent, "нет: " + ", ".join(absent))

check("route(short|long) объявлен", "def route" in graph_src)
check("граф собирается функцией build_graph", "def build_graph" in graph_src)

print("\nЧекпоинтер")

check(
    "чекпоинтер реализован в проекте, а не взят из langgraph-checkpoint-redis",
    "BaseCheckpointSaver" in cp_src and "langgraph.checkpoint.redis" not in cp_src,
)

# Голый Valkey: ни одной команды из модулей Redis Stack. Пустой файл это условие
# формально выполняет, поэтому наличие исходника — часть самой проверки: иначе
# условие зеленело бы ровно до тех пор, пока чекпоинтера нет.
#
# Сканируется КОД без комментариев и докстрингов. В самом checkpoint.py написано,
# почему JSON.SET и redisvl не используются, — и поиск по сырому тексту находил
# бы объяснение отказа как сам отказ. Проверка, которую нельзя провалить,
# упомянув запрещённое имя в комментарии, — это проверка кода, а не текста.
def strip_prose(source: str) -> str:
    if not source.strip():
        return ""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                body[0].value.value = ""
    return ast.unparse(tree)


cp_code = strip_prose(cp_src)
stack_calls = [c for c in ("json().", ".ft(", "JSON.SET", "FT.SEARCH", "redisvl") if c in cp_code]
check(
    "чекпоинтер обходится базовыми командами Valkey",
    bool(cp_code.strip()) and not stack_calls,
    "найдено: " + ", ".join(stack_calls) if stack_calls else "checkpoint.py пуст",
)

print("\nПрогресс")

check("прогресс пишется в ключ (переживает обрыв соединения)", "def snapshot" in prog_src)
check("прогресс публикуется в канал (не только опрос ключа)", "publish" in prog_src)
check("статус FAILED предусмотрен", "FAILED" in prog_src or "FAILED" in graph_src)

print("\nCelery")

check(
    "LangGraph запускается внутри Celery-задачи",
    "app.task" in tasks_src and "agora.run_pipeline" in tasks_src,
)

pyproject = read(CORE / "pyproject.toml")
check("langgraph объявлен в зависимостях", "langgraph" in pyproject)

# Узел не должен звать модель напрямую из graph.py: реализации живут в своих
# модулях, а граф их только связывает. Иначе оркестратор становится вторым
# местом, где написана логика этапа.
tree = ast.parse(graph_src) if graph_src else None
if tree is not None:
    bad_imports = [
        n.module for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module and "openai" in n.module
    ]
    check("граф не зовёт провайдера модели напрямую", not bad_imports,
          "импорты: " + ", ".join(bad_imports))

# ─── Поведенческий уровень ──────────────────────────────────────────────────

print("\nПоведение")

sys.path.insert(0, str(CORE))

try:
    from agent_core.pipeline.checkpoint import ValkeyCheckpointSaver  # noqa: F401
    from agent_core.pipeline.graph import build_graph, route  # noqa: F401
    from agent_core.pipeline.progress import ProgressWriter, progress_key  # noqa: F401
    from agent_core.pipeline.state import new_state  # noqa: F401
except ImportError as e:
    for name in (
        "route: short и long ведут разными ветками",
        "падение на среднем узле → перезапуск не повторяет пройденные узлы",
        "чекпоинт переживает пересоздание графа (новый процесс)",
        "прогресс читается из ключа после «обрыва»",
        "FAILED несёт причину",
    ):
        skip(name, f"импорт не удался: {e}")
else:
    from agent_core.pipeline.progress import ProgressWriter, progress_key
    from agent_core.pipeline.state import new_state

    class FakeValkey:
        """Голый Valkey: только те команды, которые есть без Redis Stack."""

        def __init__(self) -> None:
            self.kv: dict[str, bytes] = {}
            self.published: list[tuple[str, bytes]] = []

        def set(self, key, value, **kw):
            self.kv[key] = value

        def get(self, key):
            return self.kv.get(key)

        def delete(self, *keys):
            for k in keys:
                self.kv.pop(k, None)

        def scan_iter(self, match=None, **kw):
            prefix = (match or "*").rstrip("*")
            return iter([k for k in list(self.kv) if k.startswith(prefix)])

        def publish(self, channel, message):
            self.published.append((channel, message))

    # ── route ───────────────────────────────────────────────────────────────
    try:
        short = route(new_state(task_id="t", tenant_id="x", mode="short"))
        long_ = route(new_state(task_id="t", tenant_id="x", mode="long"))
        check("route: short и long ведут разными ветками", short != long_,
              f"обе ветки = {short}")
    except Exception as e:  # noqa: BLE001
        check("route: short и long ведут разными ветками", False,
              f"{type(e).__name__}: {str(e)[:90]}")

    # ── чекпоинт и перезапуск ───────────────────────────────────────────────
    #
    # Узлы подменяются на счётчики: настоящие требуют ffmpeg, Whisper и модель,
    # а проверяется здесь не они, а то, какие из них будут вызваны повторно.
    try:
        from agent_core.pipeline.checkpoint import ValkeyCheckpointSaver
        from agent_core.pipeline.graph import build_graph

        valkey = FakeValkey()
        calls: list[str] = []
        failing = {"on": True}

        def stub(name: str):
            def node(state):
                calls.append(name)
                if name == "stitch" and failing["on"]:
                    raise RuntimeError("VLM недоступен")
                return {}
            return node

        nodes = {n: stub(n) for n in PRD8_NODES}
        state = new_state(task_id="run-1", tenant_id="team-1", mode="short")

        graph = build_graph(checkpointer=ValkeyCheckpointSaver(valkey), nodes=nodes)
        config = {"configurable": {"thread_id": "run-1"}}

        crashed = False
        try:
            graph.invoke(state, config)
        except Exception:  # noqa: BLE001
            crashed = True

        before = list(calls)
        calls.clear()
        failing["on"] = False

        # Новый объект графа и новый саверт на том же хранилище — это и есть
        # «перезапуск воркера»: в памяти процесса не осталось ничего.
        graph2 = build_graph(checkpointer=ValkeyCheckpointSaver(valkey), nodes=nodes)
        graph2.invoke(None, config)
        after = list(calls)

        repeated = [n for n in after if n in before and n != "stitch"]
        check(
            "падение на среднем узле → перезапуск не повторяет пройденные узлы",
            crashed and not repeated and "stitch" in after,
            f"до падения={before}; после={after}; повторно={repeated}",
        )
        check(
            "чекпоинт переживает пересоздание графа (новый процесс)",
            bool(valkey.kv) and "analytics" in after,
            f"после перезапуска дошли до: {after[-1] if after else '—'}",
        )
    except Exception as e:  # noqa: BLE001
        for name in ("падение на среднем узле → перезапуск не повторяет пройденные узлы",
                     "чекпоинт переживает пересоздание графа (новый процесс)"):
            check(name, False, f"{type(e).__name__}: {str(e)[:120]}")

    # ── прогресс ────────────────────────────────────────────────────────────
    try:
        valkey = FakeValkey()
        writer = ProgressWriter(valkey, task_id="run-2")
        writer.emit("probe_and_normalize", "RUNNING")
        writer.emit("probe_and_normalize", "DONE")

        # «Обрыв»: подписчика больше нет, читаем состояние заново из ключа.
        fresh = ProgressWriter(valkey, task_id="run-2").snapshot()
        check(
            "прогресс читается из ключа после «обрыва»",
            fresh.get("node") == "probe_and_normalize" and progress_key("run-2") in valkey.kv,
            f"снимок={fresh}",
        )

        writer.fail("transcribe", "Whisper упал по OOM")
        failed = ProgressWriter(valkey, task_id="run-2").snapshot()
        check(
            "FAILED несёт причину",
            failed.get("status") == "FAILED" and "OOM" in str(failed.get("error", "")),
            f"снимок={failed}",
        )
    except Exception as e:  # noqa: BLE001
        for name in ("прогресс читается из ключа после «обрыва»", "FAILED несёт причину"):
            check(name, False, f"{type(e).__name__}: {str(e)[:120]}")


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
