# Gates: enrich personas in batches

OWNS: services/agent-core/agent_core/persona/enrich.py, services/agent-core/tests/test_enrich_batches.py, docs/gates/enrich-batches.md

Scope: обогащение персон партиями по пять сохраняет параллелизм, порядок результата, прогресс и отказоустойчивость.

- [ ] G0: ledger проходит синтаксическую проверку unlazy
  CHECK: node .claude/skills/unlazy/scripts/gate-lint.mjs docs/gates/enrich-batches.md
  EXPECT: LINT OK
  EVIDENCE: pending

- [ ] G1: поведенческий тест подтверждает параллелизм, порядок и прогресс без внешних ключей
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -c 'import sys; sys.path.insert(0, "tests"); import test_enrich_batches as t; t.test_batch_parallelism_order_and_progress(); t.test_duplicate_cache_keys_in_one_batch_pay_once(); print("ENRICH_BATCH_BEHAVIOR_PASSED")'
  EXPECT: ENRICH_BATCH_BEHAVIOR_PASSED
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G2: весь набор worker-тестов, кроме известного image-only dependency gate и отдельного identity-теста, зелёный
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py --ignore=tests/test_dependencies_declared.py && echo ENRICH_BATCH_WORKER_TESTS_PASSED
  EXPECT: ENRICH_BATCH_WORKER_TESTS_PASSED
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G3: worker проходит обязательный ruff без замечаний
  CHECK: python3 -m ruff check . && echo ENRICH_BATCH_RUFF_PASSED
  EXPECT: ENRICH_BATCH_RUFF_PASSED
  CWD: services/agent-core
  EVIDENCE: pending
