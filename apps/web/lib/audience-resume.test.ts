import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import {
  buildAudienceResumePayload,
  canResumeAudience,
  decideAudienceResume,
  failedAudienceSummary,
  survivorCountLabel,
} from "./audience-resume.ts";

const root = process.cwd();

const FAILED = {
  id: "set-1",
  size: 40,
  status: "failed" as const,
  generatedCount: 14,
  error: "соединение с моделью оборвалось после 14 персон",
  generationConfig: { size: 40, seed: 17, use_llm: true },
  settingsSnapshot: { personaTemperature: 0.4, provider: "stored" },
  corpusSnapshotId: "snapshot-1",
};

test("продолжение возможно только для failed", () => {
  assert.equal(canResumeAudience("failed"), true);
  assert.equal(canResumeAudience("generating"), false);
  assert.equal(canResumeAudience("ready"), false);
});

test("счётчик уцелевших персон показывает заказанное количество", () => {
  assert.equal(survivorCountLabel(FAILED), "14 из 40");
});

test("причина failed и объяснение продолжения не подменяются общим текстом", () => {
  assert.deepEqual(failedAudienceSummary(FAILED), {
    status: "failed",
    reason: FAILED.error,
    survivors: "14 из 40",
    resumeExplanation: "Дописать недостающих персон, не собирать набор заново",
  });
  assert.equal(failedAudienceSummary({ ...FAILED, status: "ready" }), null);
});

test("payload продолжения содержит снимки строки набора и resume=true", () => {
  assert.deepEqual(buildAudienceResumePayload(FAILED, "tenant-1"), {
    persona_set_id: "set-1",
    tenant_id: "tenant-1",
    config: FAILED.generationConfig,
    corpus_snapshot_id: "snapshot-1",
    settings_snapshot: FAILED.settingsSnapshot,
    resume: true,
  });
});

test("решение маршрута отказывает готовому набору и чужому набору", () => {
  assert.deepEqual(decideAudienceResume(null, "tenant-1"), { kind: "missing" });
  assert.deepEqual(
    decideAudienceResume({ ...FAILED, status: "ready" }, "tenant-1"),
    { kind: "not-resumable", status: "ready" },
  );
});

function read(relativePath: string): string {
  const path = join(root, relativePath);
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

test("resume route exists and keeps the generation task name", () => {
  const route = read("app/api/persona-sets/[id]/resume/route.ts");
  assert.notEqual(route, "", "маршрут продолжения не создан");
  assert.match(route, /POST/);
  assert.match(route, /enqueueAudience/);
});

test("resume route carries the explicit resume flag", () => {
  const route = read("app/api/persona-sets/[id]/resume/route.ts");
  assert.match(route, /decideAudienceResume/);
});

test("resume payload uses snapshots stored on the set", () => {
  const route = read("app/api/persona-sets/[id]/resume/route.ts");
  assert.match(route, /decideAudienceResume/);
  assert.doesNotMatch(route, /buildSettingsSnapshot/);
});

test("persona set data exposes failure details and both snapshots", () => {
  const personas = read("lib/server/personas.ts");
  assert.match(personas, /settings_snapshot/);
  assert.match(personas, /corpus_snapshot_id/);
  assert.match(personas, /error/);
  assert.match(personas, /generated_count/);
});

test("failed audience cards expose the survivor count and exact reason", () => {
  const registry = read("components/agora/AudienceRegistry.tsx");
  const page = read("app/personas/sets/[id]/page.tsx");
  assert.match(registry, /failed/);
  assert.match(registry, /generatedCount|generated_count/);
  assert.match(registry, /error/);
  assert.match(page, /failed/);
  assert.match(page, /failure\.reason/);
});
