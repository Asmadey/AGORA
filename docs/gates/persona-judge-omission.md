# Gates: persona judge omission

OWNS: prompts/persona.validate.md, infra/postgres/init/*persona_validate*.sql, services/agent-core/agent_core/persona/validate.py, evals/tests/test_persona_judge_omission.py, evals/tests/test_task26_prompt_studio.py, GATES.md

Scope: stop the persona judge from treating omitted attributes and internally sampled attribute combinations as defects, while preserving real contradiction checks and prompt seeding.

- [ ] G1: static prompt, seed, docstring, and preservation checks pass
  CHECK: python3 evals/tests/test_persona_judge_omission.py --static
  EXPECT: STATIC PERSONA JUDGE CHECKS PASSED
  EVIDENCE: pending

- [ ] G2: the three production cases are evaluated by the live judge, or honestly skipped without credentials
  CHECK: python3 evals/tests/test_persona_judge_omission.py --behavior
  EXPECT: /(?:BEHAVIORAL PERSONA JUDGE PASS|BEHAVIORAL PERSONA JUDGE SKIP)/
  EVIDENCE: pending

- [ ] G3: prompt-studio seed synchronization remains green
  CHECK: python3 evals/tests/test_task26_prompt_studio.py
  EXPECT: /OK.*тексты в засеве совпадают с файлами/
  EVIDENCE: pending

- [ ] G4: the complete worker regression suite passes with external model variables removed
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py
  EXPECT: /passed/
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G5: worker lint passes
  CHECK: python3 -m ruff check .
  EXPECT: All checks passed!
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G6: the gate ledger itself passes structural lint
  CHECK: node .claude/skills/unlazy/scripts/gate-lint.mjs GATES.md
  EXPECT: LINT OK
  EVIDENCE: pending
