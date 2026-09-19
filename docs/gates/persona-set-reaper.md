# Gates: persona set reaper and resumable generation

OWNS: GATES.md, AGENTS.md, evals/run_in_worker.sh, services/agent-core/agent_core/persona/**, services/agent-core/agent_core/maintenance/**, services/agent-core/agent_core/celery_app.py, services/agent-core/tests/test_dependencies_declared.py, services/agent-core/tests/test_persona_set_reaper.py, services/agent-core/tests/test_persona_generation_resume.py, services/agent-core/tests/test_persona_set_vanished.py, services/agent-core/tests/test_persona_validation_pool.py, infra/postgres/init/56_persona_sets_progress_at.sql, infra/preflight.py, infra/deploy.sh

Scope: аудитория записывается партиями, докачивается после сбоя, зависшие наборы переводятся в failed, а предполётная проверка видит активную генерацию.

- [ ] G0: ledger проходит структурную проверку
  CHECK: node .claude/skills/unlazy/scripts/gate-lint.mjs GATES.md
  EXPECT: LINT OK
  EVIDENCE: pending

- [ ] G1: реапер переводит просроченный набор в failed и оставляет свежий generating без изменений
  CHECK: python3 -m pytest -q tests/test_persona_set_reaper.py -k 'stale or fresh' && echo G1_REAPER_OK
  EXPECT: G1_REAPER_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G2: resume делает ровно 28 вызовов обогащения для набора 12 из 40 и не трогает записанный префикс
  CHECK: python3 -m pytest -q tests/test_persona_generation_resume.py -k 'resume_tail' && echo G2_RESUME_TAIL_OK
  EXPECT: G2_RESUME_TAIL_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G3: ready появляется только после записи всех size строк, а generated_count равен числу строк
  CHECK: python3 -m pytest -q tests/test_persona_generation_resume.py -k 'ready_only_when_complete' && echo G3_READY_OK
  EXPECT: G3_READY_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G4: повтор Celery после сбоя продолжает с хвоста и не пересоздаёт записанные персоны
  CHECK: python3 -m pytest -q tests/test_persona_generation_resume.py -k 'retry_resumes' && echo G4_RETRY_OK
  EXPECT: G4_RETRY_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G5: preflight отказывает при generating и пропускает наборы, когда все они ready
  CHECK: python3 -m pytest -q tests/test_persona_set_reaper.py -k 'preflight' && echo G5_PREFLIGHT_OK
  EXPECT: G5_PREFLIGHT_OK
  CWD: services/agent-core
  EVIDENCE: pending
