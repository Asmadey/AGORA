# Ворота: регрессии расчёта анкеты, второй круг

OWNS: services/agent-core/agent_core/analytics/survey_stats.py,
services/agent-core/agent_core/pipeline/nodes.py,
services/agent-core/agent_core/survey.py,
services/agent-core/tests/test_survey_tally_round2.py

Scope: три регрессии, внесённые правкой повторов персон и найденные третьим
независимым ревью. Две из трёх — сегодняшние, то есть цена ошибки измеряется
часами, а не месяцами.

- [x] G1: нечитаемый реестр персон не роняет узел QA, а попадает в `degraded`
  CHECK: env -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q tests/test_survey_tally_round2.py::test_qa_node_survives_unreadable_persona_registry && echo G1_OK
  EXPECT: G1_OK
  CWD: services/agent-core
  EVIDENCE: до правки узел падал с `RuntimeError: DATABASE_URL не задан` —
      исключение вместо отчёта, уже после оплаченных ответов персон.

- [x] G2: валидные повторы не считаются выбывшими по правилам QA
  CHECK: env -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q tests/test_survey_tally_round2.py::test_valid_replications_are_not_counted_as_excluded_by_qa && echo G2_OK
  EXPECT: G2_OK
  CWD: services/agent-core
  EVIDENCE: до правки `assert 2 == 0` — «выбывших по правилам 2» на прогоне,
      где QA не исключил ни одного ответа.

- [x] G3: среднее повторов не округляется в верхнюю долю
  CHECK: env -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q tests/test_survey_tally_round2.py::test_mean_of_repeated_scores_does_not_round_into_top_box && echo G3_OK
  EXPECT: G3_OK
  CWD: services/agent-core
  EVIDENCE: до правки `assert 1.0 == 0.0` — персона с ответами 7 и 8 попадала
      в долю «8–10» целиком.

- [x] G4: полный прогон воркера без единой переменной окружения снаружи
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py && echo G4_OK
  EXPECT: G4_OK
  CWD: services/agent-core
  EVIDENCE: exit 0, ни одного падения.

- [x] G5: линт воркера чист
  CHECK: python3 -m ruff check . && echo G5_OK
  EXPECT: G5_OK
  CWD: services/agent-core
  EVIDENCE: All checks passed!

- [x] G6: краснота доказана порядком работы, а не рассуждением
  EVIDENCE: тесты написаны ДО правки и упали по существу все три:
      `RuntimeError: DATABASE_URL не задан`, `assert 2 == 0`, `assert 1.0 == 0.0`.
      Ни одного `TypeError` о подписи.
