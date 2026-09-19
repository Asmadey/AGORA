# Gates: dependency declaration versus worker environment

OWNS: services/agent-core/tests/test_dependencies_declared.py, services/agent-core/tests/test_dependencies_gate.py, docs/gates/dep-test-skip.md

Scope: keep undeclared imports as failures while treating declared worker-only packages that are absent on the developer host as an explicit skip.

- [ ] G1: the dependency gate fails for an undeclared import and skips a declared package that is not installed
  CHECK: python3 -m pytest -q -rs tests/test_dependencies_gate.py tests/test_dependencies_declared.py
  EXPECT: /3 passed, 1 skipped/
  CWD: services/agent-core
  EVIDENCE: `/Users/asmadey/.venv/main/bin/python -m pytest -q -rs tests/test_dependencies_gate.py tests/test_dependencies_declared.py` -> 3 passed, 1 skipped; the skip lists the six declared worker packages. With the gate body rolled back, the same contract was 1 passed, 1 failed on faster_whisper.

- [ ] G2: the complete worker regression suite runs without provider credentials and without ignoring the dependency test
  CHECK: env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py
  EXPECT: /passed|skipped/
  CWD: services/agent-core
  EVIDENCE: `env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL /Users/asmadey/.venv/main/bin/python -m pytest -q --ignore=tests/test_audience_identity.py` -> exit 0. System python3 has no pytest, so the existing project venv was used.

- [ ] G3: worker lint is clean
  CHECK: python3 -m ruff check .
  EXPECT: /All checks passed/
  CWD: services/agent-core
  EVIDENCE: `/Users/asmadey/.venv/main/bin/python -m ruff check .` -> All checks passed.
