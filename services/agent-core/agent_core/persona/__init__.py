# agent_core.persona package — Persona Generator (задача #5)
#
# Генерация синтетических персон по методологии PRD §10:
#   1. Сэмплирование по реальным долям (сериал×город×сегмент)
#   2. Калибровка баллов по реальным средним корпуса
#   3. Стилевое + аргументативное заземление на verbatims
#   4. Ценности ВЦИОМ → DNA
#   5. Сегмент-ориентированная установка к контенту
#   6. Представитель сегмента, не копия
#
# Детерминизм: один seed → один воспроизводимый результат.

from agent_core.persona.generator import (
    CorpusDistribution,
    GenerationConfig,
    PersonaGenerator,
    generate_personas,
)

__all__ = [
    "CorpusDistribution",
    "GenerationConfig",
    "PersonaGenerator",
    "generate_personas",
]