"""Контракт гейта зависимостей: незаявленное падает, средовое пропускается."""

from __future__ import annotations

from pathlib import Path

import pytest
import test_dependencies_declared as dependencies_gate

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_missing_undeclared_import_stays_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Вымышленный импорт, которого нет в pyproject, нельзя замаскировать SKIP."""
    name = "fixture_dependency_that_is_not_declared"
    assert name not in PYPROJECT.read_text("utf-8")

    monkeypatch.setattr(
        dependencies_gate,
        "external_imports",
        lambda: {name: {"agent_core/fixture.py"}},
    )
    monkeypatch.setattr(dependencies_gate, "find_spec", lambda module: None)

    with pytest.raises(AssertionError, match="не объявлено в pyproject"):
        dependencies_gate.test_every_import_resolves()


def test_missing_declared_import_is_a_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Объявленный, но отсутствующий тяжёлый пакет означает средовой SKIP."""
    name = "faster_whisper"
    assert "faster-whisper" in PYPROJECT.read_text("utf-8")

    monkeypatch.setattr(
        dependencies_gate,
        "external_imports",
        lambda: {name: {"agent_core/asr/transcribe.py"}},
    )
    monkeypatch.setattr(dependencies_gate, "find_spec", lambda module: None)

    with pytest.raises(pytest.skip.Exception, match="объявлен.*не установлен"):
        dependencies_gate.test_every_import_resolves()


def test_installed_undeclared_import_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Установленность не заменяет объявление в pyproject."""
    name = "fixture_dependency_that_is_installed_but_not_declared"
    assert name not in PYPROJECT.read_text("utf-8")

    monkeypatch.setattr(
        dependencies_gate,
        "external_imports",
        lambda: {name: {"agent_core/fixture.py"}},
    )
    monkeypatch.setattr(dependencies_gate, "find_spec", lambda module: object())

    with pytest.raises(AssertionError, match="не объявлено в pyproject"):
        dependencies_gate.test_every_import_resolves()
