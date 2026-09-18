"use client";

import { Loader2, RotateCcw, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { blockedReason, type BlockedSet } from "@/lib/audience-delete";
import { isFailedAudience, type AudienceStatus } from "@/lib/audience-resume";

/** Действия, доступные только для сорвавшегося набора. */
export function AudienceSetActions({
  id,
  status,
}: {
  id: string;
  status: AudienceStatus;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isFailedAudience(status)) return null;

  async function resume() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/persona-sets/${id}/resume`, { method: "POST" });
      const data = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/audience", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [id] }),
      });
      const data = (await response.json()) as {
        error?: string;
        blocked?: BlockedSet[];
      };
      if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
      if (data.blocked?.length) {
        throw new Error(blockedReason(data.blocked[0]));
      }
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void resume()}
          disabled={busy}
          title="Дописать недостающих персон, не собирать набор заново"
          className="inline-flex items-center gap-1.5 rounded-md border border-ink px-3 py-1.5 text-xs font-medium transition-colors hover:bg-ink hover:text-white disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
          Продолжить
        </button>
        <button
          type="button"
          onClick={() => void remove()}
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-1.5 text-xs text-danger transition-colors hover:bg-danger-soft disabled:opacity-40"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Удалить
        </button>
      </div>
      <p className="text-xs text-slate">Продолжение допишет только недостающих персон.</p>
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}
