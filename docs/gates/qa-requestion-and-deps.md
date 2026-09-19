# Gates: QA requestion and dependency declarations

OWNS: services/agent-core/agent_core/qa/**, services/agent-core/agent_core/pipeline/nodes.py, services/agent-core/agent_core/respondent/requestion.py, services/agent-core/tests/test_requestion.py, services/agent-core/tests/test_dependencies_declared.py, services/agent-core/tests/test_dependencies_gate.py, docs/gates/qa-requestion-and-deps.md

Scope: keep informative QA flags visible without paying for a requestion and require every external import to be declared

- [ ] G1: an informative low-score flag remains visible while the product QA node makes zero requestion model calls
  CHECK: cd services/agent-core && env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q tests/test_requestion.py -k product_qa_keeps_informative_flag_without_requestion && echo "informative requestion gate passed"
  EXPECT: informative requestion gate passed
  EVIDENCE: pending

- [ ] G2: an installed external import with no pyproject declaration is classified as undeclared and fails the dependency test
  CHECK: cd services/agent-core && python3 -m pytest -q tests/test_dependencies_gate.py -k installed_undeclared && echo "dependency declaration gate passed"
  EXPECT: dependency declaration gate passed
  EVIDENCE: pending

- [ ] G3: the complete worker regression suite passes without model environment variables
  CHECK: cd services/agent-core && env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py && echo "worker regression passed"
  EXPECT: worker regression passed
  EVIDENCE: pending

- [ ] G4: worker lint passes
  CHECK: cd services/agent-core && python3 -m ruff check . && echo "ruff check passed"
  EXPECT: ruff check passed
  EVIDENCE: pending
