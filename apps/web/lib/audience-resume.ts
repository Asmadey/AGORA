import type { AudiencePayload } from "@/lib/server/queue";

export type AudienceStatus = "generating" | "ready" | "failed";

export interface AudienceSetForResume {
  id: string;
  size: number;
  status: AudienceStatus;
  generatedCount: number;
  error: string | null;
  generationConfig: Record<string, unknown>;
  settingsSnapshot: Record<string, unknown>;
  corpusSnapshotId: string | null;
}

export type AudienceResumeDecision =
  | { kind: "missing" }
  | { kind: "not-resumable"; status: AudienceStatus }
  | { kind: "queued"; payload: AudiencePayload & { resume: true } };

export function isFailedAudience(status: AudienceStatus): boolean {
  return status === "failed";
}

export function canResumeAudience(status: AudienceStatus): boolean {
  return isFailedAudience(status);
}

/** Числа, а не процент: размер заказа важен для решения, достаточно ли остатка. */
export function survivorCountLabel(set: Pick<AudienceSetForResume, "generatedCount" | "size">): string {
  return `${set.generatedCount} из ${set.size}`;
}

export function failedAudienceSummary(
  set: Pick<AudienceSetForResume, "status" | "error" | "generatedCount" | "size">,
) {
  if (!isFailedAudience(set.status)) return null;
  return {
    status: set.status,
    reason: set.error ?? "",
    survivors: survivorCountLabel(set),
    resumeExplanation: "Дописать недостающих персон, не собирать набор заново",
  };
}

/** Payload возобновления собирается только из сохранённых параметров набора. */
export function buildAudienceResumePayload(
  set: AudienceSetForResume,
  tenantId: string,
): AudiencePayload & { resume: true } {
  if (!canResumeAudience(set.status)) {
    throw new Error("продолжить можно только для набора в статусе failed");
  }
  return {
    persona_set_id: set.id,
    tenant_id: tenantId,
    config: set.generationConfig,
    corpus_snapshot_id: set.corpusSnapshotId,
    settings_snapshot: set.settingsSnapshot,
    resume: true,
  };
}

/** Решение маршрута после tenant-scoped чтения строки набора. */
export function decideAudienceResume(
  set: AudienceSetForResume | null,
  tenantId: string,
): AudienceResumeDecision {
  if (!set) return { kind: "missing" };
  if (!canResumeAudience(set.status)) return { kind: "not-resumable", status: set.status };
  return { kind: "queued", payload: buildAudienceResumePayload(set, tenantId) };
}

export function splitAudienceSets<T extends { status: AudienceStatus }>(sets: T[]) {
  return {
    failed: sets.filter((set) => isFailedAudience(set.status)),
    active: sets.filter((set) => !isFailedAudience(set.status)),
  };
}
