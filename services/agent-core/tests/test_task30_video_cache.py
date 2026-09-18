"""Перезапуск использует готовый результат родителя на уровне узла."""
from __future__ import annotations

import json
from types import SimpleNamespace

from agent_core.frames.analyze import MemoryCache
from agent_core.pipeline import nodes
from agent_core.pipeline.state import new_state


class CountingVlm:
    calls = 0

    def __init__(self, *args, **kwargs):
        self.calls = 0

    def analyze(self, *, image: bytes, prompt: str) -> dict:
        self.calls += 1
        CountingVlm.calls += 1
        return {"summary": image.decode()}

def _state(tmp_path, *, parent: str | None, video: str) -> dict:
    state = new_state(task_id="child", tenant_id="team", video_ref=video, parent_task_id=parent)
    state["panel_refs"] = [{"path": str(tmp_path / "panel.jpg"), "timestamp_sec": 0,
                             "end_sec": 1, "is_cut": True, "frame_times": [], "frames": []}]
    (tmp_path / "panel.jpg").write_bytes(b"panel")
    return state

def test_same_parent_material_skips_vlm_node(monkeypatch, tmp_path) -> None:
    CountingVlm.calls = 0
    monkeypatch.setattr(
        nodes, "_parent_video_result",
        lambda state, *, load_pack=None: (
            [{"summary": "saved"}],
            "материал совпал с родителем parent",
        ),
    )
    monkeypatch.setattr(
        nodes, "_vlm_cache",
        lambda state: (_ for _ in ()).throw(AssertionError("cache must not be needed")),
    )
    monkeypatch.setattr("agent_core.frames.analyze.QwenVlmClient", CountingVlm)
    result = nodes.analyze_chunks(_state(tmp_path, parent="parent", video="same"))
    assert CountingVlm.calls == 0
    with open(result["chunk_analyses_ref"], encoding="utf-8") as stream:
        assert json.load(stream) == [{"summary": "saved"}]

def test_different_parent_material_keeps_tenant_cache(monkeypatch, tmp_path) -> None:
    CountingVlm.calls = 0
    cache = MemoryCache()
    monkeypatch.setattr(
        nodes,
        "_model_config",
        lambda state: SimpleNamespace(vlm_model="test-model"),
    )
    monkeypatch.setattr(
        nodes, "_parent_video_result",
        lambda state, *, load_pack=None: (
            None,
            "материал отличается от родительского; кэш разбора не использован",
        ),
    )
    monkeypatch.setattr(nodes, "_vlm_cache", lambda state: cache)
    monkeypatch.setattr("agent_core.frames.analyze.QwenVlmClient", CountingVlm)
    nodes.analyze_chunks(_state(tmp_path, parent="parent", video="other"))
    assert CountingVlm.calls == 1
    assert len(cache.store) == 1

def test_without_parent_uses_normal_path(monkeypatch, tmp_path) -> None:
    CountingVlm.calls = 0
    cache = MemoryCache()
    monkeypatch.setattr(
        nodes,
        "_model_config",
        lambda state: SimpleNamespace(vlm_model="test-model"),
    )
    monkeypatch.setattr(
        nodes,
        "_parent_video_result",
        lambda state, *, load_pack=None: (None, None),
    )
    monkeypatch.setattr(nodes, "_vlm_cache", lambda state: cache)
    monkeypatch.setattr("agent_core.frames.analyze.QwenVlmClient", CountingVlm)
    nodes.analyze_chunks(_state(tmp_path, parent=None, video="video"))
    assert CountingVlm.calls == 1
    assert len(cache.store) == 1
