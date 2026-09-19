# Ворота: визуализация результатов опроса

Задание заказчика — графики по вопросам 1–15 с колонкой «Показатель в ЦА
(14–35)» у каждого. Работа разбита на шесть этапов; ворота дописываются по
этапам, уже написанные не переписываются.

OWNS: services/agent-core/agent_core/analytics/**, services/agent-core/agent_core/pipeline/nodes.py, services/agent-core/tests/**, apps/web/lib/**, apps/web/components/agora/**, data/survey/**, packages/shared/schemas/**, docs/gates/survey-charts.md

---

## Этап 0 — фундамент: охват, знаменатель, выбывшие

Scope: расчёт анкеты получает персон прогона, доли считаются от размера охвата,
а число выбывших по правилам в блоке анкеты — настоящее.

Повод замерен, а не предположен. В боевом отчёте `6c96ea60` лежит
`audience: {total: 0, target: 0}` и `base: 0` у каждого из пятнадцати вопросов:
`_personas_for_segments` отдаёт пустой список, когда ответы несут поле
`segment`. Оптимизация написана для посегментного разреза, а `survey_tally`
через тот же аргумент берёт персон для возрастного среза и знаменателя. Пока это
так, колонка «14–35» пуста на ЛЮБОМ прогоне, и рисовать поверх неё графики
нечего.

Там же `survey.excluded_by_qa: 0` при девяти реально выброшенных ответах из
двадцати: `survey_tally` получает уже отфильтрованный список и честно считает по
нему ноль.

- [ ] G0.1: Узел аналитики отдаёт в блок анкеты всех персон прогона, когда
      ответы несут собственный `segment`
  CHECK: python3 -m pytest -q tests/test_survey_audience_scope.py::test_analytics_node_counts_all_run_personas && echo G01_OK
  EXPECT: G01_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.2: Срез 14–35 набирается из персон прогона по точному возрасту
  CHECK: python3 -m pytest -q tests/test_survey_audience_scope.py::test_target_slice_counts_personas_in_age_range && echo G02_OK
  EXPECT: G02_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.3: Доля варианта считается от размера охвата, а не от числа ответивших
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_choice_share_uses_scope_size && echo G03_OK
  EXPECT: G03_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.4: Доля 8–10 и группы шкалы считаются от того же охвата
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_scale_shares_use_scope_size && echo G04_OK
  EXPECT: G04_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.5: Средний балл остаётся средним по ответившим и молчанием не
      разбавляется
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_scale_mean_counts_only_answered && echo G05_OK
  EXPECT: G05_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.6: Пустой охват даёт `null`, а не ноль, и не делит на ноль
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_empty_scope_gives_null_not_zero && echo G06_OK
  EXPECT: G06_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.7: Блок анкеты называет настоящее число выбывших по правилам
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_survey_block_reports_real_excluded_count && echo G07_OK
  EXPECT: G07_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.8: Прежние тесты расчётов анкеты не потеряны, а пересчитаны: файл
      `test_survey_stats.py` содержит не меньше 22 тестов и проходит целиком
  CHECK: python3 -c "import re,sys,pathlib; n=len(re.findall(r'^def test_', pathlib.Path('tests/test_survey_stats.py').read_text('utf-8'), re.M)); sys.exit(0 if n>=22 else print(f'тестов стало {n}, было 22') or 1)" && python3 -m pytest -q tests/test_survey_stats.py && echo G08_OK
  EXPECT: G08_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.9: Полный прогон воркера без единой переменной окружения снаружи
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py && echo G09_OK
  EXPECT: G09_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.10: Линт воркера чист
  CHECK: python3 -m ruff check . && echo G10_OK
  EXPECT: G10_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G0.11: Краснота тестов G0.1–G0.7 доказана откатом файлов реализации, а не
      рассуждением: с прежними `survey_stats.py` и `nodes.py` они падают по
      существу (неверное число), а не `TypeError` о подписи
  EVIDENCE: pending
