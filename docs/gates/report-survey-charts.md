# Gates: survey charts in the report

OWNS: apps/web/lib/report-survey-charts.ts, apps/web/lib/report-survey-charts.test.ts, apps/web/lib/report-survey.ts, apps/web/components/agora/ReportBody.tsx, apps/web/components/agora/SurveyQuestionChart.tsx, apps/web/components/agora/survey-charts/**

Scope: connect the report survey section to the existing chart primitives while
keeping the 14-35 slice, its respondent count, service options, measured zeroes,
and suppressed null values visible.

- [x] G1: every survey question chart model has the expected kind and rows
  CHECK: cd apps/web && node --conditions=react-server --test lib/report-survey-charts.test.ts
  EXPECT: # tests 3 and # pass 3
  EVIDENCE: exit=0; 3 tests, 3 passed, 0 failed

- [x] G2: report parsing and chart primitive helpers stay green
  CHECK: cd apps/web && node --conditions=react-server --test lib/report-survey.test.ts lib/report-view.test.ts lib/report-charts.test.ts lib/survey-charts.test.ts
  EXPECT: # fail 0
  EVIDENCE: exit=0; 72 tests, 72 passed, 0 failed

- [x] G3: the complete web package passes tests, types, and production build
  CHECK: npm test --workspace apps/web && cd apps/web && npx tsc --noEmit && cd ../.. && npm run build
  EXPECT: exit code 0
  EVIDENCE: npm test 619/619 passed; npx tsc --noEmit exit=0; npm run build exit=0

- [x] G4: no whitespace errors remain in the task diff
  CHECK: git diff --check
  EXPECT: exit code 0
  EVIDENCE: exit=0

- [x] G5: question 7 exposes both polarity metrics without mixing them into emotion bars
  CHECK: cd apps/web && node --conditions=react-server --test lib/report-survey-charts.test.ts
  EXPECT: # pass 4
  EVIDENCE: exit=0; 4 tests, 4 passed, 0 failed; covers measured total and 14-35 shares, no metrics without reporting.groups, and null for a suppressed slice

- [x] G6: the existing polarityPairs contract and report parser remain green
  CHECK: cd apps/web && node --conditions=react-server --test lib/report-survey.test.ts
  EXPECT: # pass 26
  EVIDENCE: exit=0; 26 tests, 26 passed, 0 failed

- [x] G7: final web validation passes tests, type checking, and production build
  CHECK: npm test --workspace apps/web && cd apps/web && npx tsc --noEmit && cd ../.. && npm run build
  EXPECT: exit code 0
  EVIDENCE: npm test 630/630 passed; report-survey.test.ts 26/26 passed; npx tsc --noEmit exit=0; npm run build exit=0

- [x] G8: polarity metrics are enabled by survey data and do not spill into question 10
  CHECK: cd apps/web && node --conditions=react-server --test lib/report-survey.test.ts lib/report-survey-charts.test.ts lib/survey-reporting.test.ts
  EXPECT: exit code 0; question 7 keeps both metrics and question 10 gets none
  EVIDENCE: exit=0; 39 targeted tests passed; full web run passed 632/632

- [x] G9: the worker accepts the survey contract and remains lint-clean
  CHECK: cd services/agent-core && env -u OPENAI_BASE_URL -u OPENAI_API_KEY -u AI_MODEL python3 -m pytest -q --ignore=tests/test_audience_identity.py && python3 -m ruff check .
  EXPECT: exit code 0
  EVIDENCE: exit=0 in the project virtualenv; pytest completed all collected tests, ruff reported All checks passed!
