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
