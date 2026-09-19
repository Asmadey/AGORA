# Gates: persona validation ladder

OWNS: prompts/persona.validate.md, infra/postgres/init/58_prompts_seed_persona_validate_ladder.sql, services/agent-core/agent_core/persona/validate.py, services/agent-core/agent_core/persona/enrich.py, services/agent-core/agent_core/persona/tasks.py, services/agent-core/agent_core/schemas/responses.py, services/agent-core/tests/test_persona_validation_ladder.py, evals/tests/test_task26_prompt_studio.py, GATES.md

Scope: keep the sampled skeleton when a judge finds a prose defect, and reserve a new seed for prose that could not be repaired after the configured attempts.

- [ ] G1: the ladder is tested through observable callbacks and final persona data
  CHECK: cd services/agent-core && python3 -m pytest -q tests/test_persona_validation_ladder.py
  EXPECT: /passed/
  EVIDENCE: pending

- [ ] G2: the prompt and strict response schema agree on issue kinds and severity
  CHECK: cd services/agent-core && python3 -m pytest -q tests/test_persona_validation_ladder.py tests/test_structured_outputs.py
  EXPECT: /passed/
  EVIDENCE: pending

- [ ] G3: prompt-studio seed synchronization remains green
  CHECK: python3 evals/tests/test_task26_prompt_studio.py
  EXPECT: /OK.*тексты в засеве совпадают с файлами/
  EVIDENCE: pending

- [ ] G4: the complete worker regression suite passes without external model variables
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py
  EXPECT: /passed/
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G5: worker lint passes
  CHECK: python3 -m ruff check .
  EXPECT: /All checks passed!/
  CWD: services/agent-core
  EVIDENCE: pending

- [ ] G6: the required final tree snapshot is clean and contains the single commit
  CHECK: git status --short && git log --oneline -1 && git show --stat HEAD
  EXPECT: /GATES.md|persona\/validate.py|persona\/enrich.py|persona\/tasks.py/
  EVIDENCE: pending

ABANDON: G7 the unlazy skill and its gate-lint script are not installed in this session; manual review of this ledger is required.
