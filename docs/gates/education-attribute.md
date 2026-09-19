# Gates: образование как атрибут и критерий аудитории

OWNS: services/agent-core/agent_core/persona/generator.py, services/agent-core/tests/test_education_attribute.py, apps/web/lib/audience.ts, apps/web/lib/education.ts, apps/web/lib/education.test.ts, apps/web/components/agora/AudienceStep.tsx, apps/web/components/agora/GenerationCriteria.tsx, apps/web/app/studies/new/page.tsx, data/demography/education_by_age.json

Scope: возрастные ворота и внешние возрастные доли образования в DNA, перенормировка возрастов при выборе одного варианта, отказ от пустого пересечения, объяснение источника и видимое следствие на шаге «Резюме».

- [x] G1: ни одна персона младше 18 лет не получает высшее или неполное высшее
  CHECK: python3 -m pytest -q services/agent-core/tests/test_education_attribute.py -k underage
  EXPECT: 1 passed
  EVIDENCE: `/Users/asmadey/.venv/main/bin/python -m pytest -q tests/test_education_attribute.py` -> 7 passed

- [x] G2: реализованные доли высшего по возрастным группам совпадают с паспортом с точностью до 1 п.п.
  CHECK: python3 -m pytest -q services/agent-core/tests/test_education_attribute.py -k group_shares
  EXPECT: 1 passed
  EVIDENCE: included in the same targeted run; every group stayed within 1 p.p.

- [x] G3: выбор «есть высшее» оставляет только высшее и убирает 14-17 из состава
  CHECK: python3 -m pytest -q services/agent-core/tests/test_education_attribute.py -k restrict_has_higher
  EXPECT: 1 passed
  EVIDENCE: included in the same targeted run; 500/500 were «высшее», 14-17 was absent

- [x] G4: пересечение 14-17 + «есть высшее» отвергается понятной ошибкой
  CHECK: python3 -m pytest -q services/agent-core/tests/test_education_attribute.py -k impossible_intersection
  EXPECT: 1 passed
  EVIDENCE: included in the same targeted run; ValueError names the education/14-17 intersection

- [x] G5: один seed даёт один результат при обычном выборе и при выборе образования
  CHECK: python3 -m pytest -q services/agent-core/tests/test_education_attribute.py -k deterministic
  EXPECT: 1 passed
  EVIDENCE: included in the same targeted run; repeated filtered output was identical

- [x] G6: веб-логика и текст подсказки содержат оба режима, возрастное следствие и источник с оговорками
  CHECK: node --conditions=react-server --test apps/web/lib/education.test.ts
  EXPECT: /# pass [1-9][0-9]*/
  EVIDENCE: 6 passed

- [x] G7: полный worker regression suite passes without provider variables
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q
  EXPECT: /passed/
  CWD: services/agent-core
  EVIDENCE: `/Users/asmadey/.venv/main/bin/python -m pytest -q` -> 100% passed; system python lacked dependencies

- [x] G8: worker lint, web tests, typecheck and production build pass
  CHECK: python3 -m ruff check . && cd ../../ && npm test --workspace apps/web && cd apps/web && npx tsc --noEmit && cd ../.. && npm run lint && npm run build
  EXPECT: /success|passed|All checks passed|# pass [1-9][0-9]*/
  CWD: services/agent-core
  EVIDENCE: ruff passed; web suite 595 passed; tsc passed; lint passed; build passed
