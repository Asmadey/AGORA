# Ворота: честный расчёт анкеты с повторами и охватом

OWNS: services/agent-core/agent_core/analytics/survey_stats.py, services/agent-core/agent_core/pipeline/nodes.py, services/agent-core/tests/test_survey_tally_fixes.py, docs/gates/survey-tally-fixes.md

Scope: одна персона считается одним респондентом независимо от числа повторов,
ошибка чтения реестра персон видна в `degraded`, а подавленный срез сохраняет
раздельно число ответивших и размер охвата.

- [x] G1: три дефекта воспроизводятся через `survey_tally` и узел `analytics`
  CHECK: /Users/asmadey/.venv/main/bin/python3 -m pytest -q tests/test_survey_tally_fixes.py
  EXPECT: /3 passed/
  CWD: services/agent-core
  EVIDENCE: exit=0; три регрессионных теста зелёные после исправления

- [x] G2: существующие расчёты анкеты и доставка охвата остаются зелёными
  CHECK: /Users/asmadey/.venv/main/bin/python3 -m pytest -q tests/test_survey_stats.py tests/test_survey_denominator.py tests/test_survey_audience_scope.py
  EXPECT: /29 passed/
  CWD: services/agent-core
  EVIDENCE: exit=0; 29 тестов прошли

- [x] G3: полный воркерный прогон проходит без переменных провайдера
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL /Users/asmadey/.venv/main/bin/python3 -m pytest -q --ignore=tests/test_audience_identity.py
  EXPECT: /100%/
  CWD: services/agent-core
  EVIDENCE: exit=0; полный прогон завершён без падений

- [x] G4: линт воркера чист
  CHECK: /Users/asmadey/.venv/main/bin/python3 -m ruff check .
  EXPECT: /All checks passed!/
  CWD: services/agent-core
  EVIDENCE: exit=0; All checks passed!

- [x] G5: веб-тесты, проверка типов и production build проходят
  CHECK: npm test --workspace apps/web && cd apps/web && npx tsc --noEmit && cd ../.. && npm run build
  EXPECT: /(?:# pass [1-9][0-9]*|Compiled with warnings|Generating static pages)/
  EVIDENCE: exit=0; веб-тесты, tsc и build завершились успешно; build сохранил только известные предупреждения Edge Runtime

- [x] G6: краснота доказана на реализации до исправления
  EVIDENCE: временный stash двух файлов реализации оставил новый тест; исходный код дал три содержательных падения: `4 == 2`, отсутствует предупреждение `degraded`, `5 == 1`. После проверки реализация восстановлена.
