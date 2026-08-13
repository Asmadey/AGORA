"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";

/**
 * Удаление портрета с подтверждением вводом имени.
 *
 * Подтверждение здесь тяжелее, чем у прогона (там достаточно второго клика), и
 * это соразмерно последствиям: прогон можно повторить за деньги, а портрет,
 * дистиллированный из корпуса, восстанавливается только повторной дистилляцией
 * — то есть отдельной операцией над всем датасетом. Ввод имени отсекает
 * промах по кнопке, оставляя намеренное удаление в два действия.
 */
export function DeletePortraitButton({
  portraitId,
  name,
}: {
  portraitId: string;
  name: string;
}) {
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/portraits/${portraitId}`, { method: "DELETE" });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        setError(payload.error ?? `сервер ответил ${res.status}`);
        return;
      }
      router.push("/portraits");
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!asking) {
    return (
      <button
        type="button"
        onClick={() => setAsking(true)}
        className="rounded-full border border-danger/40 px-4 py-2 text-sm text-danger transition-colors hover:bg-danger-soft"
      >
        Удалить портрет
      </button>
    );
  }

  return (
    <div className="max-w-md space-y-3 rounded-lg border border-danger/30 bg-danger-soft/50 p-4">
      <p className="text-sm">
        Введите название портрета, чтобы подтвердить: <b>{name}</b>
      </p>
      <input
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        autoFocus
        aria-label="Подтверждение названием"
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring"
      />
      {error && <p className="text-xs text-danger">{error}</p>}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={remove}
          disabled={busy || typed.trim() !== name}
          className="inline-flex items-center gap-2 rounded-full bg-danger px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          Удалить навсегда
        </button>
        <button
          type="button"
          onClick={() => {
            setAsking(false);
            setTyped("");
            setError(null);
          }}
          className="rounded-full px-4 py-2 text-sm text-slate hover:text-ink"
        >
          Отмена
        </button>
      </div>
    </div>
  );
}
