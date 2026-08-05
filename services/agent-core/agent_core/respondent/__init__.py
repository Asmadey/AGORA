"""
Respondent-агенты (задача #18).

Каждая персона проходит анкету в структурной изоляции: в её срезе только своя
DNA, материал видео и анкета. Ни чужих персон, ни чужих ответов.
"""

from __future__ import annotations

from .diversity import distinct_2, score_stdev
from .run import BATCH_SIZE, SurveyOutcome, run_survey

__all__ = ["BATCH_SIZE", "SurveyOutcome", "run_survey", "distinct_2", "score_stdev"]
