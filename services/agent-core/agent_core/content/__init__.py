"""
Склейка материала в Content Pack (задача #17).

Стадия REDUCE конвейера: транскрипт с диаризацией (#15) и VLM-разбор сцен (#16)
сводятся в единый таймлайн по глобальным таймкодам.
"""

from __future__ import annotations

from .pack import ContentPack, build_pack

__all__ = ["ContentPack", "build_pack"]
