# Gates: QA low score

OWNS: services/agent-core/agent_core/qa/**, services/agent-core/agent_core/analytics/aggregate.py, services/agent-core/tests/test_qa_low_score_not_gating.py, docs/gates/qa-low-score.md

Scope: keep subjective score and retention combinations visible to operators without excluding their answers from analytics, while preserving objective QA gates

- [ ] G1: low score with intent to finish is flagged but survives the aggregate, and an out-of-scale score still gates
  CHECK: cd services/agent-core && python3 -m pytest -q tests/test_qa_low_score_not_gating.py && echo "qa low score gate passed"
  EXPECT: qa low score gate passed
  EVIDENCE: pending

- [ ] G2: the complete worker regression suite runs without model environment variables
  CHECK: cd services/agent-core && env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py && echo "worker regression passed"
  EXPECT: worker regression passed
  EVIDENCE: pending

- [ ] G3: worker lint passes
  CHECK: cd services/agent-core && python3 -m ruff check . && echo "ruff check passed"
  EXPECT: ruff check passed
  EVIDENCE: pending
