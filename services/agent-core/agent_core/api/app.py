"""Точка входа uvicorn: ``uvicorn agent_core.api.app:app``.

Реэкспортирует FastAPI-приложение из ``agent_core.api`` (``__init__.py``).
"""

from agent_core.api import app

__all__ = ["app"]