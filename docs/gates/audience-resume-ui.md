# Gates: resume failed audience sets

OWNS: apps/web/app/api/audience/**, apps/web/app/api/persona-sets/**, apps/web/app/personas/**, apps/web/app/audience/**, apps/web/components/agora/AudienceRegistry.tsx, apps/web/components/agora/AudienceSetActions.tsx, apps/web/lib/audience-callers.test.ts, apps/web/lib/audience-delete.ts, apps/web/lib/audience-delete.test.ts, apps/web/lib/audience-resume.ts, apps/web/lib/audience-resume.test.ts, apps/web/lib/server/personas.ts, apps/web/lib/server/queue.ts, packages/shared/openapi/agora.openapi.json, GATES.md

Scope: show failed audience sets with their failure details, allow only safe deletion, and resume generation from the stored snapshots.

- [x] G1: failed-set rules distinguish safe deletion, generating deletion, and deletion blocked by runs
  CHECK: node --conditions=react-server --test lib/audience-resume.test.ts lib/audience-delete.test.ts
  EXPECT: /# pass [1-9][0-9]*/
  CWD: apps/web
  EVIDENCE: automatic-evidence=v1; definition-sha256=826334f9a33b63b65d757ed333d6bc32a196a38510318ae4bbb85ba4b1dfac27; exit=0; EXPECT=matched; output-sha256=1a8f4e880010f935c8f7a23d934ae9c0fb1ebeea71d31e3013fd75aedc7e56ff; output-bytes=5374; shell=/bin/sh; cwd=/private/tmp/AGORA-web-resume/apps/web; path=1d9b16c405b9/30 entries

- [x] G2: the resume route and first-generation path preserve and enqueue the stored payload snapshots
  CHECK: node --conditions=react-server --test lib/audience-resume.test.ts
  EXPECT: /# pass [1-9][0-9]*/
  CWD: apps/web
  EVIDENCE: automatic-evidence=v1; definition-sha256=648907c58df9f8e2eb49270fbd92af306dc58b44901f697ff8dbc9756d9667fc; exit=0; EXPECT=matched; output-sha256=52e8682c7cb0ee3016a0898c27002d8b9b96a93cf751838d9e53a1d20826e0d8; output-bytes=2857; shell=/bin/sh; cwd=/private/tmp/AGORA-web-resume/apps/web; path=1d9b16c405b9/30 entries

- [x] G3: the full web test suite passes
  CHECK: npm test --workspace apps/web
  EXPECT: /# pass [1-9][0-9]*/
  EVIDENCE: automatic-evidence=v1; definition-sha256=31ee1682edd42addc27e7770de90d5335b59f88b9e46b5452de2c430462eb1ba; exit=0; EXPECT=matched; output-sha256=ba10661564aa476e5a369d714e85f820c0139e01e0c136b550e0fded549c3eb7; output-bytes=170170; shell=/bin/sh; cwd=/private/tmp/AGORA-web-resume; path=1d9b16c405b9/30 entries

- [x] G4: TypeScript has no diagnostics
  CHECK: npx tsc --noEmit && echo "GATE tsc passed"
  EXPECT: GATE tsc passed
  CWD: apps/web
  EVIDENCE: automatic-evidence=v1; definition-sha256=d17c9d1b92f6fa8e074cf133f21820c1012bb42beaa910dd9a83a099813b3635; exit=0; EXPECT=matched; output-sha256=082d4755e660ba8dc493f59462a7a1a81b57dbfb6cbc2beadbacfca099fb8bd3; output-bytes=16; shell=/bin/sh; cwd=/private/tmp/AGORA-web-resume/apps/web; path=1d9b16c405b9/30 entries

- [x] G5: the production web build succeeds
  CHECK: npm run build && echo "GATE build passed"
  EXPECT: GATE build passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=58a7e0e3be485883d193e123475e9a949274723f148ba9bf5a9f2bd9050cc91c; exit=0; EXPECT=matched; output-sha256=7eb53a11bb654bbf24778463ba102898de99a60d7ba8a738a30866a63ff27ac2; output-bytes=6083; shell=/bin/sh; cwd=/private/tmp/AGORA-web-resume; path=1d9b16c405b9/30 entries

- [x] G6: the rendered failed-set screens expose status, exact error, survivor count, and the two allowed actions
  EVIDENCE: Reviewed apps/web/components/agora/AudienceRegistry.tsx and apps/web/app/personas/sets/[id]/page.tsx: failed cards/panel render status, the stored reason unchanged, generatedCount out of size, and the failed-only Продолжить/Удалить actions.
