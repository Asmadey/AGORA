# Ворота: ценности по возрасту

Ворота проверяют наблюдаемый состав выданных персон и вклад признака в подбор.
Таблица `data/values/values_by_age_vciom.json` остается неизменной.

## G1 - Доли ценностей зависят от возраста

CHECK: `python3 evals/tests/test_task05_persona_generator.py`

EXPECT: вывод содержит проверки долей для `35-44` и `18-24`, а также явную
проверку, что `60+` отличается от `18-24` по служению Отечеству.

## G2 - Возрастная подстановка 14-17

CHECK: `python3 evals/tests/test_task05_persona_generator.py`

EXPECT: вывод содержит успешную проверку, что `14-17` использует доли `18-24`.

## G3 - Детерминизм и непустое множество

CHECK: `python3 evals/tests/test_task05_persona_generator.py`

EXPECT: вывод содержит успешные проверки повторного seed и минимум одной
ценности у каждой сгенерированной персоны.

## G4 - Restrict передает возраст ценностям

CHECK: `python3 evals/tests/test_task05_persona_generator.py`

EXPECT: вывод содержит успешную проверку, что ограничение возраста сохраняется
в выданных персонах и влияет на выбор ценностей.

## G5 - Grounding использует ВЦИОМ по возрасту

CHECK: `python3 -m pytest -q tests/test_values_grounding.py`

EXPECT: все тесты файла проходят, а ожидаемые доли берутся из
`values_by_age_vciom.json`, не из `value_counts` корпуса.

## G6 - Отсутствующее поле корпуса не является несовпадением

CHECK: `python3 evals/tests/test_task25_matching.py`

EXPECT: вывод содержит успешную проверку, что запись без личных ценностей
получает ненулевой score по остальным признакам и поле
`psychographics_and_values.important_values` не используется.
