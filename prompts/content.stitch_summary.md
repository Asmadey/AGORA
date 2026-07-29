# content.stitch_summary (seed)
Склейка чанков в единое понимание видео. Переменные: {{chunk_analyses}},
{{transcript_diarized}}, {{content_title}}.
---
Собери из по-кадровых разборов и транскрипта с диаризацией единый документ «понимание видео»
по глобальному таймлайну (транскрипт — позвоночник). Материал:
Транскрипт со спикерами: {{transcript_diarized}}
Разборы сцен (JSON по таймкодам): {{chunk_analyses}}

Верни JSON:
{
  "title": "{{content_title}}",
  "synopsis": "<связный синопсис по фактам материала>",
  "timeline": [{"start":"<tc>","end":"<tc>","scene":"<что происходит>","dialogue":"<ключевые реплики+спикер>","mood":"<...>"}],
  "acts": [{"act":1,"summary":"<...>","key_moments":["<tc: момент>"]}],
  "characters": [{"name_or_role":"<...>","arc":"<роль в сюжете>"}],
  "themes": ["<тема>"], "tone": "<общий тон>",
  "notable_elements": {"cinematography":"<...>","music_or_sound":"<...>","violence_level":"<...>","costumes_realism":"<...>"}
}
Опирайся ТОЛЬКО на переданный материал. Ничего не додумывай. Верни только JSON.
