import "server-only";

import { readFileSync } from "node:fs";
import path from "node:path";

import type { RespondentSession } from "@agora/shared/types/respondent-session";

/**
 * Доступ к grounding-корпусу из веб-приложения (задача #23).
 *
 * Зеркало services/agent-core/agent_core/grounding/corpus.py: тот же файл, те
 * же выборки, те же имена. Расхождение между этими двумя модулями означает, что
 * фронт и воркер считают по-разному одно и то же — заметить это по симптомам
 * почти невозможно.
 *
 * Корпус read-only и общий для всех арендаторов, поэтому здесь нет ни tenant_id,
 * ни обращения к базе. Файл читается один раз за жизнь процесса: 1.8 МБ, 165
 * записей — перечитывать нечего, меняется он только вместе с коммитом.
 *
 * "server-only": файл лежит на диске, в браузер он не поедет.
 */

const CORE_SCORES = [
  "overall_impression",
  "plot",
  "acting",
  "music",
  "cinematography",
] as const;

export type CoreScoreKey = (typeof CORE_SCORES)[number];

export interface CorpusMeta {
  version: number;
  records: number;
  sha256: string;
  sources: string[];
}

// process.cwd() в Next.js — apps/web, поэтому до корня монорепо два уровня вверх.
const REPO_ROOT = path.resolve(process.cwd(), "..", "..");
const DATASET = path.join(REPO_ROOT, "data", "grounding", "unified_respondent_sessions.json");
const META = path.join(REPO_ROOT, "data", "grounding", "corpus.meta.json");

let sessionsCache: RespondentSession[] | null = null;
let metaCache: CorpusMeta | null = null;

function readJson<T>(file: string): T {
  try {
    return JSON.parse(readFileSync(file, "utf8")) as T;
  } catch (error) {
    // Явная ошибка вместо пустого массива: «корпус не прочитан» и «корпус пуст»
    // должны различаться, иначе метрика молча посчитается по нулю записей.
    throw new Error(
      `не удалось прочитать корпус ${path.basename(file)}: ${(error as Error).message}`,
    );
  }
}

/** Все записи корпуса. */
export function loadSessions(): readonly RespondentSession[] {
  if (!sessionsCache) {
    const data = readJson<RespondentSession[]>(DATASET);
    if (!Array.isArray(data) || data.length === 0) {
      throw new Error("корпус должен быть непустым массивом записей");
    }
    sessionsCache = data;
  }
  return sessionsCache;
}

/** Паспорт корпуса: версия, число записей, хеш, источники. */
export function loadMeta(): CorpusMeta {
  if (!metaCache) {
    const raw = readJson<{
      version: number;
      records: number;
      sha256: string;
      provenance: { sources: string[] };
    }>(META);
    metaCache = {
      version: raw.version,
      records: raw.records,
      sha256: raw.sha256,
      sources: raw.provenance.sources,
    };
  }
  return metaCache;
}

export function bySource(sourceFile: string): readonly RespondentSession[] {
  return loadSessions().filter((r) => r.source_file === sourceFile);
}

export function byAgeGroup(ageGroup: string): readonly RespondentSession[] {
  return loadSessions().filter((r) => r.socio_demographics.age_group === ageGroup);
}

/**
 * Доли значений социодемографического поля. Ровно это сравнивает метрика
 * persona_grounding с распределениями сгенерированных персон.
 */
export function distribution(field: "gender" | "age_group" | "geo" | "city"): Record<string, number> {
  const sessions = loadSessions();
  const counts = new Map<string, number>();
  for (const r of sessions) {
    const value = String(r.socio_demographics[field]);
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  const result: Record<string, number> = {};
  for (const key of [...counts.keys()].sort()) {
    result[key] = (counts.get(key) as number) / sessions.length;
  }
  return result;
}

/** Средние по пяти критериям. Порог калибровки |средние−реальные| ≤ 1.0. */
export function meanScores(): Record<CoreScoreKey, number> {
  const sessions = loadSessions();
  const out = {} as Record<CoreScoreKey, number>;
  for (const key of CORE_SCORES) {
    const sum = sessions.reduce((acc, r) => acc + r.agora_core_scores_1_to_10[key], 0);
    out[key] = sum / sessions.length;
  }
  return out;
}

export function meanNps(): number {
  const sessions = loadSessions();
  const sum = sessions.reduce(
    (acc, r) => acc + r.perception_and_retention.recommendation_nps_1_to_10,
    0,
  );
  return sum / sessions.length;
}

export function sources(): string[] {
  return [...new Set(loadSessions().map((r) => r.source_file))].sort();
}
