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

- [x] G0.1: Узел аналитики отдаёт в блок анкеты всех персон прогона, когда
      ответы несут собственный `segment`
  CHECK: python3 -m pytest -q tests/test_survey_audience_scope.py::test_analytics_node_counts_all_run_personas && echo G01_OK
  EXPECT: G01_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=719335f9124aafc9ffeb951fa88813a4fdaaddd499b77e898b042de42d6fb787; exit=0; EXPECT=matched; output-sha256=de25f4dc94f48bc9b2adec18a75dcd1c14faa4c2823f1eeea3bfed7058a5264c; output-bytes=87; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.2: Срез 14–35 набирается из персон прогона по точному возрасту
  CHECK: python3 -m pytest -q tests/test_survey_audience_scope.py::test_target_slice_counts_personas_in_age_range && echo G02_OK
  EXPECT: G02_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=dc1c98b9cd1f6f85ec6a83cb70338c5a5426d47b98a263fdba65af8603123749; exit=0; EXPECT=matched; output-sha256=658c4843822561dc4595f215c3c71703f5f9bf5ea964352f373d2850f86d4593; output-bytes=87; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.3: Доля варианта считается от размера охвата, а не от числа ответивших
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_choice_share_uses_scope_size && echo G03_OK
  EXPECT: G03_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=21b9e16b5b4c411b8b77d1cec1a5ae38dfeff071e4ad7d0123e11b4823957a27; exit=0; EXPECT=matched; output-sha256=ed8972a047935eba2780d747b5a59cd2fa8b51dae7d84a9d8f96364a31ad564d; output-bytes=87; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.4: Доля 8–10 и группы шкалы считаются от того же охвата
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_scale_shares_use_scope_size && echo G04_OK
  EXPECT: G04_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=2eb6ad82e36f9085b873f97a5b0d1663a3ece621caaa1620b5820e9deba85ee1; exit=0; EXPECT=matched; output-sha256=280911ebc50ea0bfa6ad46a9d58645f7002a3563e7b65e3eca9e4c8956166466; output-bytes=87; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.5: Средний балл остаётся средним по ответившим и молчанием не
      разбавляется
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_scale_mean_counts_only_answered && echo G05_OK
  EXPECT: G05_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=ceaa7778ce1e63cde688179c4e7ec79074636af71fc32e3369a79e2a27a852db; exit=0; EXPECT=matched; output-sha256=a8b49ea012a3d840a6b433ae3d70482d6a714c4999a9e32615160022bb31bb51; output-bytes=87; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.6: Пустой охват даёт `null`, а не ноль, и не делит на ноль
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_empty_scope_gives_null_not_zero && echo G06_OK
  EXPECT: G06_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=43b05f70fcf6cf82be03037254f42c5f839b081a448f5764975c650c76b2d1f7; exit=0; EXPECT=matched; output-sha256=ea6ba7419cce8f17ae760369c9753015ab7be93e72409720ad59ca2ad19561f0; output-bytes=87; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.7: Блок анкеты называет настоящее число выбывших по правилам
  CHECK: python3 -m pytest -q tests/test_survey_denominator.py::test_survey_block_reports_real_excluded_count && echo G07_OK
  EXPECT: G07_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=b0be544d19d2d70b3a28b984fc9e722b341afad2d3716c6e0e7d69f9ace8463d; exit=0; EXPECT=matched; output-sha256=586ea37cb62990e4eb78ffac82fdda4dcc24f1c9f6836f78737fab925da19821; output-bytes=87; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.8: Прежние тесты расчётов анкеты не потеряны, а пересчитаны: файл
      `test_survey_stats.py` содержит не меньше 22 тестов и проходит целиком
  CHECK: python3 -c "import re,sys,pathlib; n=len(re.findall(r'^def test_', pathlib.Path('tests/test_survey_stats.py').read_text('utf-8'), re.M)); sys.exit(0 if n>=22 else print(f'тестов стало {n}, было 22') or 1)" && python3 -m pytest -q tests/test_survey_stats.py && echo G08_OK
  EXPECT: G08_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=45212da489808da6d71f93f6a548dc496af91f729aed6d8b121624920eeb47e6; exit=0; EXPECT=matched; output-sha256=1edca3e587e2dcc9284f52b21d427df53fc16c52fd514d7f5440506bb336fe96; output-bytes=87; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.9: Полный прогон воркера без единой переменной окружения снаружи
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py && echo G09_OK
  EXPECT: G09_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=d105e980973bfeec4423eb4e562d90364de8b18dd288f466855ba331f6d29192; exit=0; EXPECT=matched; output-sha256=724c390363864d5462384c693d5c56b38600d7d55aa2c4ad893fb8fe54efeea1; output-bytes=1127; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.10: Линт воркера чист
  CHECK: python3 -m ruff check . && echo G10_OK
  EXPECT: G10_OK
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=425429f3fcc07af547c7932982c064b3f18f8a3f8d360e5e94f04db83230a58a; exit=0; EXPECT=matched; output-sha256=82ae9624e18b66dbeb2f325debef25e6271015f9012f53fc1d2a48f6d3f2e562; output-bytes=26; shell=/bin/sh; cwd=/Users/asmadey/AntiGravity/AGORA/.claude/worktrees/survey-results-charts-7be05a/services/agent-core; path=f116f76ee75b/24 entries

- [x] G0.11: Краснота тестов G0.1–G0.7 доказана откатом файлов реализации, а не
      рассуждением: с прежними `survey_stats.py` и `nodes.py` они падают по
      существу (неверное число), а не `TypeError` о подписи
  EVIDENCE: откат выполнен оркестратором, а не принят по отчёту исполнителя:
      `git checkout HEAD~1 -- survey_stats.py aggregate.py nodes.py`, затем
      прогон обоих новых файлов тестов. Шесть падений, все по существу:
      `assert 0 == 20` и `assert 0 == 9` (персоны не доехали до анкеты),
      `assert 0.7273 == 0.4` дважды (доля от ответивших вместо охвата),
      `assert {'yes': 0.0} is None` (пустой охват давал ноль),
      `assert 0 == 9` (блок анкеты сообщал ноль выбывших). Ни одного
      `TypeError` о подписи. Седьмой тест,
      `test_scale_mean_counts_only_answered`, на прежнем коде ПРОШЁЛ — и это
      верно: среднее по ответившим он и должен был оставить неизменным, он
      сторожит регресс, а не чинимый дефект. Реализация возвращена
      `git checkout HEAD -- services/agent-core/`, рабочее дерево чисто,
      все десять исполнимых ворот перепроверены `--reverify`.
