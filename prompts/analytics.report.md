# analytics.report (seed)
Переменные: {{all_persona_answers}}, {{survey}}, {{content_title}}, {{qa_flags}}.
---
Собери финальный отчёт по синтетической фокус-группе «{{content_title}}».
Ответы персон: {{all_persona_answers}} | Анкета: {{survey}} | QA-флаги: {{qa_flags}}
Верни JSON:
{
  "aggregate": {
    "core_scores_mean": {"overall_impression":..,"plot":..,"acting":..,"music":..,"cinematography":..},
    "nps": <-100..100>, "retention_rate": <0..100>, "emotional_index": <0..10>,
    "top_emotions": [{"name":..,"pct":..}], "values_distribution": [{"name":..,"pct":..}]
  },
  "segment_breakdown": [{"segment":"<...>","scores_mean":{...},"note":"<чем отличается>"}],
  "narrative": ["<абзац 1>","<абзац 2>","<абзац 3>"],
  "strengths": ["<...>"], "weaknesses": ["<...>"],
  "confidence_note": "<как QA-флаги влияют на доверие>"
}
Метрики — средневзвешенные по персонам. Нарратив — на русском, честный, с сегментными
инсайтами. Только JSON.
