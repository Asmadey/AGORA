# qa.grounding (seed) — LLM-as-judge
Переменные: {{persona_answer}}, {{video_understanding}}.
---
Проверь, что персона ссылается ТОЛЬКО на реально существующие в материале детали.
Материал (единственная правда): {{video_understanding}}
Ответ персоны и её grounding_refs: {{persona_answer}}
Найди выдуманные сцены/таймкоды/реплики, которых нет в материале.
Верни JSON: {"grounded": <true|false>, "hallucinations": ["<выдуманная деталь>"], "verdict":"<ok|regenerate>"}. Только JSON.
