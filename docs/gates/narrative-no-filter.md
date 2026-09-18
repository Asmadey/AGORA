# Gates: narrative support metadata without filtering

OWNS: GATES.md, services/agent-core/agent_core/analytics/report.py, services/agent-core/agent_core/chat/agent.py, prompts/analytics.report.md, infra/postgres/init/55_prompts_seed_analytics_narrative_support.sql, evals/tests/test_task20_analytics.py, evals/state/tasks.json

Scope: keep every non-empty narrative statement in the report while preserving support observability, chat grounding flags, and prompt seed synchronization

- [ ] G0: this ledger has valid executable definitions
  CHECK: node .claude/skills/unlazy/scripts/gate-lint.mjs GATES.md
  EXPECT: LINT OK
  EVIDENCE: pending

- [ ] G1: analytics report keeps unsupported narrative and records support counts
  CHECK: python3 evals/tests/test_task20_analytics.py
  EXPECT: Итог: OK=
  EVIDENCE: pending

- [ ] G2: chat still marks unsupported replies instead of dropping them
  CHECK: python3 evals/tests/test_task28_chat.py
  EXPECT: Итог: OK=
  EVIDENCE: pending

- [ ] G3: prompt file and database seed remain synchronized
  CHECK: python3 evals/tests/test_task26_prompt_studio.py
  EXPECT: Итог: OK=
  EVIDENCE: pending

- [ ] G4: the complete worker test suite passes without provider environment
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py && echo FULL_AGENT_CORE_OK
  EXPECT: FULL_AGENT_CORE_OK
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G5: worker lint passes
  CHECK: python3 -m ruff check . && echo RUFF_OK
  EXPECT: RUFF_OK
  CWD: services/agent-core
  EVIDENCE: pending
