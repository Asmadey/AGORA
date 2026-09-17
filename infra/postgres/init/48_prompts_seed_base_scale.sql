-- AGORA · 48 · respondent.user: базовые критерии на шкале 0–10
--
-- Решение о нулевой оценке принято после первоначального засева промпта.
-- Применённые миграции не редактируются: точечно синхронизируем дефолтный
-- промпт с prompts/respondent.user.md.

BEGIN;

UPDATE prompts
SET template = replace(
      replace(
        template,
        '    "overall_impression": <1..10>,
    "plot": <1..10>,
    "acting": <1..10>,
    "music": <1..10>,
    "cinematography": <1..10>',
        '    "overall_impression": <0..10>,
    "plot": <0..10>,
    "acting": <0..10>,
    "music": <0..10>,
    "cinematography": <0..10>'
      ),
      '- Баллы 1–10 целые. Эмоции — из того, что реально вызвало видео.',
      '- Баллы 0–10 целые: 0 — совсем не понравилось, 10 — очень понравилось.
  Ноль — законная оценка, а не отказ отвечать.
  Эмоции — из того, что реально вызвало видео.'
    ),
    version = version + 1
WHERE tenant_id IS NULL
  AND is_default
  AND key = 'respondent.user'
  AND template LIKE '%"overall_impression": <1..10>%';

COMMIT;
