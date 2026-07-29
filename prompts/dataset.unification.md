# dataset.unification (seed)
Сборка grounding-датасета из XLS+DOCX. Переменные: {{xls_rows}}, {{docx_context}}.
---
Собери профильные карточки респондентов (8 секций PRD §10.1) из анкет XLS и контекста DOCX.
XLS-строки: {{xls_rows}} | Контекст фокус-групп (DOCX): {{docx_context}}
Для каждого респондента верни объект: respondent_id, source_file, content_under_test,
experiment_metadata (город, target_audience_segment, transcript_source_file),
socio_demographics (нормализуй: gender муж/жен; age_group 14-17/18-24/25-34/35-44/45-59/60+;
geo столицы/центры субъектов/иные НП), psychographics_and_values (ВЦИОМ),
agora_core_scores_1_to_10 (5 критериев; распарсь текстовые шкалы «Отлично/Хорошо» в 1-10),
perception_and_retention, qualitative_verbatims (why_impression/idea_comprehension_comment/
general_impression_comment), focus_group_verbatims (3-4 живые цитаты из DOCX сегмента),
all_survey_responses (полный словарь вопрос→ответ, ничего не терять).
Склейка по (сериал×город×сегмент). Верни только валидный JSON-массив.
