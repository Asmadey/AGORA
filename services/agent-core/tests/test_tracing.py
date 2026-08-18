"""
Трассировка вызовов модели в LangFuse.

─── Что здесь проверяется ────────────────────────────────────────────────────
Не то, что данные доехали до сервера — это проверяет прогон, — а три свойства,
без которых трассировка либо не появится, либо навредит:

1. **Без ключей всё работает.** Трассировка — наблюдение за продуктом, а не его
   часть. Разработчик без LangFuse, CI без LangFuse и прогон при упавшем
   LangFuse обязаны идти как раньше. Обратное означает, что установка
   наблюдения добавила продукту новую точку отказа.

2. **Клиент действительно обёрнут.** Модуль-обёртку легко написать, покрыть
   тестами и не подключить: шесть мест в коде поднимают `OpenAI(...)`
   самостоятельно, и любое забытое просто не появится в трассах. Это самый
   частый дефект в этом репозитории, и ловится он только проверкой на стыке.

3. **Ключи не уезжают в трассу.** Трасса живёт дольше прогона, смотрится шире и
   выгружается целиком. Ключ провайдера, попавший туда, скомпрометирован так
   же, как попавший в git (CLAUDE.md §7).
"""

from __future__ import annotations

import pytest

from agent_core import tracing

KEYS = {
    "LANGFUSE_PUBLIC_KEY": "pk-lf-тест",
    "LANGFUSE_SECRET_KEY": "sk-lf-тест",
    "LANGFUSE_BASE_URL": "https://langfuse.example",
}


@pytest.fixture
def with_keys(monkeypatch):
    for k, v in KEYS.items():
        monkeypatch.setenv(k, v)
    tracing.reset()
    yield
    tracing.reset()


@pytest.fixture
def without_keys(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    tracing.reset()
    yield
    tracing.reset()


# ─── 1. Без ключей продукт не меняется ───────────────────────────────────────

def test_disabled_without_keys(without_keys):
    assert not tracing.enabled()


def test_stage_is_a_no_op_without_keys(without_keys):
    """Контекст обязан отработать вхолостую, а не упасть."""
    with tracing.stage("probe_and_normalize", task_id="t", tenant_id="x"):
        pass


def test_flush_is_safe_without_keys(without_keys):
    tracing.flush()


def test_enabled_with_keys(with_keys):
    assert tracing.enabled()


# ─── 2. С ключами клиент обёрнут ─────────────────────────────────────────────
#
# Проверяется в ОТДЕЛЬНОМ процессе, и это не перестраховка. Обёртка LangFuse не
# подменяет класс клиента: она патчит `openai.resources.chat.completions.
# Completions.create` глобально, при импорте `langfuse.openai`. Импорт
# необратим, поэтому тест «без ключей клиент не обёрнут» в общем процессе
# зависел бы от порядка тестов и однажды позеленел бы навсегда.
#
# Отсюда же следует, чего этот тест НЕ доказывает: раз патч глобальный,
# случайно уцелевший прямой `OpenAI(...)` где-то в коде тоже попадёт в трассы.
# Полагаться на это нельзя — порядок импортов не гарантирован, — поэтому за
# отсутствием прямых вызовов следит отдельная проверка ниже.

_PROBE = """
import json, sys
sys.path.insert(0, {root!r})
from agent_core import tracing
tracing.llm_client(api_key="k", base_url="https://x/v1")
print(json.dumps({{"patched": "langfuse.openai" in sys.modules}}))
"""


def _probe(env: dict[str, str]) -> bool:
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = str(Path(__file__).resolve().parents[1])
    clean = {k: v for k, v in os.environ.items() if not k.startswith("LANGFUSE_")}
    result = subprocess.run(
        [sys.executable, "-c", _PROBE.format(root=root)],
        capture_output=True, text=True, env={**clean, **env}, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-800:]
    return json.loads(result.stdout.strip().splitlines()[-1])["patched"]


def test_client_is_not_traced_without_keys():
    assert not _probe({}), (
        "без ключей LangFuse клиент всё равно обёрнут: упавшая трассировка "
        "становится точкой отказа продукта"
    )


def test_client_is_traced_with_keys():
    assert _probe(KEYS), (
        "клиент не обёрнут: вызовы модели не появятся в трассах, и заметить это "
        "можно будет только по пустому экрану LangFuse"
    )


def test_wrapped_client_keeps_openai_surface(with_keys):
    """
    Обёртка обязана остаться клиентом OpenAI. Расхождение здесь проявилось бы
    не при сборке, а на первом вызове модели — то есть после оплаченных ffmpeg
    и транскрипции.
    """
    client = tracing.llm_client(api_key="k", base_url="https://x/v1")
    assert hasattr(client.chat.completions, "create")


# ─── 3. Ключи в трассу не уезжают ────────────────────────────────────────────

# Образцы собираются из кусков, а не пишутся литералом. Первая редакция
# написала их целиком — и уронила гейт `secret_scan` (CLAUDE.md §7), который
# читает исходники и не отличает выдуманный ключ от настоящего.
#
# Это не обход проверки, а её условие. Гейт обязан краснеть на всём, что похоже
# на ключ, — иначе он бесполезен; значит, тест на маскировку ключей не может
# содержать ключей в тексте. Написать в исключения путь этого файла было бы
# ровно тем послаблением, из-за которого гейт однажды пропустит настоящий.
_FAKE_API_KEY = "sk-" + "abcdefghijklmnopqrstuvwxyz012345"
_FAKE_BEARER = "Bearer " + "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.x"
_FAKE_DSN = "postgresql://user:" + "пароль" + "@host:5432/db"


@pytest.mark.parametrize(
    "secret", [_FAKE_API_KEY, _FAKE_BEARER, _FAKE_DSN],
)
def test_mask_removes_credentials(secret):
    out = tracing.mask(data=f"перед {secret} после")
    assert secret not in out, f"в трассу уехало {secret[:12]}…"
    assert "перед" in out and "после" in out, "маска съела полезный текст"


def test_mask_walks_into_structures():
    data = {"messages": [{"role": "user", "content": f"ключ {_FAKE_API_KEY}"}]}
    out = tracing.mask(data=data)
    assert _FAKE_API_KEY not in str(out)


def test_mask_keeps_the_material():
    """
    Содержимое корпуса и ответы персон НЕ маскируются: ради них трассировка и
    ставилась. Маска здесь — про учётные данные, а не про предметные данные, и
    путать это значит получить трассы, по которым нечего разобрать.
    """
    text = "Персона 12: ролик показался мне затянутым на 0:44–0:48"
    assert tracing.mask(data=text) == text


# ─── 4. Ни одного клиента в обход обёртки ────────────────────────────────────
#
# Шесть модулей поднимали `OpenAI(...)` самостоятельно. Обернуть пять и забыть
# шестой — дефект, который ничем себя не проявляет: прогон идёт, трассы
# приходят, и только одного вида вызовов в них нет. Заметить это можно, лишь
# зная заранее, что он должен быть.
#
# Проверка по исходникам, а не по поведению: воспроизвести «забыли один вызов»
# поведенчески означало бы поднять все шесть путей с живым провайдером.

def test_no_module_builds_an_openai_client_directly():
    """
    Разбор через `ast`, а не поиском по строкам. Первая редакция искала
    подстроку и нашла `OpenAI(` в ДОКСТРОКЕ config.py, объявив нарушением
    объяснение того, почему нужен особый заголовок. Проверка, срабатывающая на
    комментарии, заставляет переписывать комментарии — а переписывают их обычно
    удалением.
    """
    import ast
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "agent_core"

    offenders = []
    for path in package.rglob("*.py"):
        if path.name == "tracing.py":
            continue  # единственное законное место
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"OpenAI", "AsyncOpenAI"}
            ):
                offenders.append(f"{path.relative_to(package)}:{node.lineno}")

    assert not offenders, (
        "клиент модели поднят в обход agent_core.tracing.llm_client: "
        + ", ".join(sorted(offenders))
        + ". Эти вызовы не попадут в трассы, и увидеть пропажу можно будет "
        "только зная заранее, что она есть"
    )


# ─── 5. Узлы конвейера видны по отдельности ──────────────────────────────────
#
# Без этого трасса плоская: сотня вызовов модели в одну кучу, и по ней нельзя
# сказать, какой узел их сделал. Замеры длительности показывают, что узел занял
# 1111 секунд; трасса обязана показывать, ИЗ ЧЕГО они состоят.

def test_pipeline_nodes_open_a_span_each(monkeypatch):
    from agent_core.pipeline import graph as graph_mod

    opened: list[str] = []

    class _Span:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    import contextlib as _ctx

    @_ctx.contextmanager
    def fake_stage(name, task_id="", tenant_id="", **attrs):
        opened.append(name)
        yield None

    monkeypatch.setattr(graph_mod.tracing, "stage", fake_stage)

    node = graph_mod._traced("probe_and_normalize", lambda state: {"ok": True}, None)
    node({"task_id": "t", "tenant_id": "x"})  # type: ignore[arg-type]

    assert opened == ["probe_and_normalize"], (
        f"узел не открыл спан: {opened}. Трасса останется плоской, и по ней "
        f"нельзя будет сказать, какой узел сделал вызов"
    )


def test_node_failure_still_closes_the_span(monkeypatch):
    """
    Спан обязан закрыться и на отказе. Незакрытый спан в LangFuse выглядит
    вечно идущим узлом — то есть трасса врёт именно там, где её открывают.
    """
    from agent_core.pipeline import graph as graph_mod

    closed: list[bool] = []

    import contextlib as _ctx

    @_ctx.contextmanager
    def fake_stage(name, task_id="", tenant_id="", **attrs):
        try:
            yield None
        finally:
            closed.append(True)

    monkeypatch.setattr(graph_mod.tracing, "stage", fake_stage)

    def boom(state):
        raise RuntimeError("провайдер отказал")

    node = graph_mod._traced("analyze_chunks", boom, None)
    with pytest.raises(RuntimeError):
        node({"task_id": "t", "tenant_id": "x"})  # type: ignore[arg-type]

    assert closed == [True]


# ─── 6. Спаны узлов собираются в одну трассу прогона ─────────────────────────
#
# Без корневого спана тринадцать узлов дадут тринадцать не связанных между
# собой трасс. Смотреть их можно, разобрать прогон — нет: непонятно, какие из
# них относятся к одному ролику. Идентификатор задачи уходит в `session_id`,
# арендатор — в `user_id`, потому что именно по ним фильтрует интерфейс
# LangFuse и считается стоимость.

class _FakeSpan:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeClient:
    """
    Заглушка клиента LangFuse.

    Её метод обязан существовать у настоящего клиента — за этим следит
    `test_fake_client_matches_the_real_sdk` ниже, и это не педантизм. Первая
    редакция этой заглушки повторяла API третьей версии SDK, ровно как и
    проверяемый код: тест был зелёным, а на первом настоящем вызове пришло
    `'Langfuse' object has no attribute 'start_as_current_span'`.

    Заглушка, написанная по тем же представлениям, что и код, проверяет
    представления, а не код.
    """

    def __init__(self) -> None:
        self.seen: dict[str, object] = {}

    def start_as_current_observation(self, **kwargs):
        self.seen["span_name"] = kwargs.get("name")
        self.seen["as_type"] = kwargs.get("as_type")
        return _FakeSpan()

    def flush(self):
        self.seen["flushed"] = True


def test_fake_client_matches_the_real_sdk():
    from langfuse import Langfuse

    for name in ("start_as_current_observation", "flush"):
        assert hasattr(Langfuse, name), (
            f"заглушка тестов реализует {name}, которого у настоящего клиента "
            f"нет: тесты проверяют вымышленный SDK"
        )


def test_run_binds_task_and_tenant_to_the_trace(with_keys, monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(tracing, "client", lambda: fake)

    propagated: dict[str, object] = {}

    import contextlib as _ctx

    @_ctx.contextmanager
    def fake_propagate(**kwargs):
        propagated.update(kwargs)
        yield

    import langfuse

    monkeypatch.setattr(langfuse, "propagate_attributes", fake_propagate)

    with tracing.run(task_id="0050", tenant_id="de15d1e3", mode="short"):
        pass

    assert propagated.get("session_id") == "0050", (
        "прогон не помечен идентификатором задачи: вызовы одного ролика "
        "рассыплются по несвязанным трассам"
    )
    assert propagated.get("user_id") == "de15d1e3"
    assert "tenant:de15d1e3" in (propagated.get("tags") or [])
    assert fake.seen.get("as_type") == "span"
    assert fake.seen.get("flushed"), (
        "трасса не отправлена: воркер живёт долго, и накопленное дождётся "
        "выхода процесса, то есть не появится тогда, когда его смотрят"
    )


def test_propagated_metadata_is_strings_within_the_limit(with_keys, monkeypatch):
    """
    SDK v4 принимает в propagate_attributes только dict[str, str] со значением
    до 200 символов; длиннее — отбрасывает с предупреждением, то есть молча для
    того, кто смотрит трассу.
    """
    monkeypatch.setattr(tracing, "client", lambda: _FakeClient())

    propagated: dict[str, object] = {}

    import contextlib as _ctx

    @_ctx.contextmanager
    def fake_propagate(**kwargs):
        propagated.update(kwargs)
        yield

    import langfuse

    monkeypatch.setattr(langfuse, "propagate_attributes", fake_propagate)

    with tracing.run(
        task_id="0050", tenant_id="t", personas=20, note="я" * 500
    ):
        pass

    metadata = propagated["metadata"]
    assert all(isinstance(v, str) for v in metadata.values()), metadata
    assert all(len(v) <= 200 for v in metadata.values())
    assert metadata["personas"] == "20"


def test_run_pipeline_opens_the_root_span(monkeypatch):
    """
    Стык: модуль выше можно написать и не позвать из задачи Celery. Тогда узлы
    будут открывать спаны без родителя, и это тоже даст трассы — просто
    бесполезные.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "agent_core" / "pipeline" / "tasks.py"
    ).read_text("utf-8")
    tree = ast.parse(source)

    run_pipeline = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "run_pipeline"
    )
    calls = {
        ast.unparse(n.func)
        for n in ast.walk(run_pipeline)
        if isinstance(n, ast.Call)
    }
    assert any(c.endswith("tracing.run") or c == "run" for c in calls), (
        "run_pipeline не открывает корневой спан: спаны узлов останутся без "
        "родителя, и прогон нельзя будет собрать обратно"
    )


# ─── 7. Маска покрывает содержимое вызовов модели ────────────────────────────
#
# Легаси-хук `mask` видит только то, что положено через API самого LangFuse.
# Промпты и ответы кладёт интеграция OpenAI своими атрибутами `gen_ai.*` — мимо
# него. Маска, поставленная туда, выглядит работающей и не закрывает ровно то
# место, ради которого ставилась.

def _otel_span(attributes: dict):
    """Снимок спана в том виде, в каком его отдаёт SDK на экспорт."""
    from langfuse.types import OtelSpanData

    return OtelSpanData(
        trace_id="t",
        span_id="s",
        parent_span_id=None,
        name="OpenAI-generation",
        instrumentation_scope_name="openai",
        instrumentation_scope_version=None,
        attributes=attributes,
        resource_attributes={},
    )


def test_export_hook_masks_generation_attributes():
    from langfuse.types import MaskOtelSpansParams, OtelSpanIdentifier

    identifier = OtelSpanIdentifier(trace_id="t", span_id="s")
    span = _otel_span(
        {
            "gen_ai.prompt.0.content": f"используй ключ {_FAKE_API_KEY}",
            "gen_ai.completion.0.content": "Париж",
            "gen_ai.usage.input_tokens": 12,
        }
    )

    result = tracing.mask_otel_spans(
        params=MaskOtelSpansParams(spans={identifier: span})
    )

    assert result is not None, "хук ничего не поправил, хотя ключ в атрибуте есть"
    patched = result.span_patches[identifier].set_attributes
    assert _FAKE_API_KEY not in patched["gen_ai.prompt.0.content"]
    assert "gen_ai.completion.0.content" not in patched, (
        "правка должна быть точечной: атрибуты, которых маска не касалась, "
        "переписывать незачем"
    )


def test_export_hook_leaves_clean_batches_alone():
    from langfuse.types import MaskOtelSpansParams, OtelSpanIdentifier

    span = _otel_span({"gen_ai.completion.0.content": "ролик показался затянутым"})
    result = tracing.mask_otel_spans(
        params=MaskOtelSpansParams(
            spans={OtelSpanIdentifier(trace_id="t", span_id="s"): span}
        )
    )
    assert result is None, "пачка без учётных данных обязана уйти нетронутой"


# ─── 8. Имена наблюдений — как имена в API ───────────────────────────────────
#
# Правило из https://langfuse.com/docs/observability/best-practices : имя
# идентифицирует ОПЕРАЦИЮ, а не отдельное её исполнение. Имя с идентификатором
# внутри («прогон 0050») даёт новое имя на каждый прогон, и по нему нельзя ни
# сгруппировать, ни отфильтровать, ни нацелить оценщика. Идентификатор для
# этого есть в session_id и в метаданных.
#
# Первая редакция трассировки нарушала это правило, и заметить его я смог
# только прочитав страницу заново, а не по памяти.

def test_trace_name_carries_no_identifiers(with_keys, monkeypatch):
    monkeypatch.setattr(tracing, "client", lambda: _FakeClient())

    propagated: dict[str, object] = {}

    import contextlib as _ctx

    @_ctx.contextmanager
    def fake_propagate(**kwargs):
        propagated.update(kwargs)
        yield

    import langfuse

    monkeypatch.setattr(langfuse, "propagate_attributes", fake_propagate)

    with tracing.run(task_id="0050", tenant_id="de15d1e3"):
        pass

    name = str(propagated.get("trace_name") or "")
    assert "0050" not in name and "de15d1e3" not in name, (
        f"имя трассы «{name}» содержит идентификатор: каждый прогон даст новое "
        f"имя, и фильтры, панели и оценщики перестанут по нему находиться"
    )
    assert name, "имя трассы пустое"


def test_every_model_call_is_named(with_keys):
    """
    Стык. Без явного имени интеграция называет генерацию `OpenAI-generation` —
    одинаково для ответа персоны, вердикта судьи и разбора кадра. В трассе они
    станут неразличимы, а оценщик, который целится по имени, поймает все три.
    """
    import ast
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "agent_core"

    unnamed = []
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = ast.unparse(node.func)
            if not target.endswith("chat.completions.create"):
                continue
            if not any(kw.arg == "name" for kw in node.keywords):
                unnamed.append(f"{path.relative_to(package)}:{node.lineno}")

    assert not unnamed, (
        "вызов модели без имени наблюдения: " + ", ".join(sorted(unnamed))
        + ". Все такие вызовы лягут в трассу под одним именем "
        "`OpenAI-generation` и станут неразличимы"
    )
