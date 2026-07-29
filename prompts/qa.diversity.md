# qa.diversity (seed)
Переменные: {{all_persona_answers}}, {{expected_variance}}.
---
Оцени разнообразие ответов выборки (защита от mode collapse). Ответы: {{all_persona_answers}}
Посчитай дисперсию баллов по 5 критериям и разнообразие формулировок. Сравни с ожидаемым
разбросом реальной аудитории ({{expected_variance}}).
Верни JSON: {"score_variance": {...}, "text_diversity": <0..1>, "collapsed": <true|false>,
"note": "<если схлопнулось — где>"}. Только JSON.
