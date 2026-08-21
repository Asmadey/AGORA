"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, AlertCircle } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import {
  ModelPicker,
  ReasoningControls,
  useProviderModels,
} from "@/components/agora/ModelControls";
import {
  DEFAULT_SETTINGS,
  settingsEqual,
  TEMPERATURE_STAGES,
  type TenantSettings,
} from "@/lib/settings";

/**
 * QA-судья: чем и как проверяются ответы персон.
 *
 * ─── Почему отдельный раздел, а не блок в Настройках ───────────────────────
 * Настройки отвечают на вопрос «как считать», этот раздел — на вопрос «кому
 * верить». Судья вправе быть другой моделью, чем респондент, и это не тонкая
 * настройка, а суть проверки: одна модель в обеих ролях склонна признавать
 * собственную работу верной, и доля отбраковок тогда говорит о согласии модели
 * с собой, а не о качестве ответов.
 *
 * ─── Что здесь НЕ настраивается ────────────────────────────────────────────
 * Порог уверенности для эскалации живёт в окружении (`QA_ESCALATION_CONFIDENCE`)
 * вместе с адресом второго агента. Выносить его сюда, пока сама эскалация не
 * работает, значило бы дать ручку от механизма, которого нет.
 */

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export default function QaJudgePage() {
  const [saved, setSaved] = useState<TenantSettings>(DEFAULT_SETTINGS);
  const [draft, setDraft] = useState<TenantSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [save, setSave] = useState<SaveState>({ kind: "idle" });
  const provider = useProviderModels();

  const dirty = !settingsEqual(saved, draft);
  const judgeTemperature = draft.temperatures.answerJudge;

  useEffect(() => {
    let cancelled = false;
    fetch("/api/settings")
      .then((r) => r.json())
      .then((data: { settings?: TenantSettings }) => {
        if (cancelled || !data.settings) return;
        setSaved(data.settings);
        setDraft(data.settings);
      })
      .catch(() => undefined)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  function patch(part: Partial<TenantSettings>) {
    setDraft((d) => ({ ...d, ...part }));
    setSave({ kind: "idle" });
  }

  async function submit() {
    setSave({ kind: "saving" });
    try {
      // Отправляются ВСЕ настройки, а не только судейские: маршрут принимает
      // целый объект, и частичная отправка затёрла бы соседние поля
      // умолчаниями. Черновик здесь и есть целый объект — он загружен целиком.
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const data = (await res.json()) as { settings?: TenantSettings; error?: string; details?: string[] };
      if (!res.ok) {
        setSave({
          kind: "error",
          message: [data.error, ...(data.details ?? [])].filter(Boolean).join("; "),
        });
        return;
      }
      if (data.settings) {
        setSaved(data.settings);
        setDraft(data.settings);
      }
      setSave({ kind: "ok" });
    } catch (e) {
      setSave({ kind: "error", message: (e as Error).message });
    }
  }

  return (
    <>
      <PageHeader
        title="QA судья"
        subtitle="Кто и как проверяет ответы персон перед тем, как они попадут в агрегат."
      />

      <div className="max-w-2xl space-y-6 p-8">
        {loading ? (
          <p className="text-sm text-slate">Загружаем настройки…</p>
        ) : (
          <>
            <section className="rounded-lg border border-hairline bg-card p-6">
              <h2 className="text-sm font-semibold">Модель судьи</h2>
              <p className="mt-1 text-xs leading-relaxed text-slate">
                Судить может другая модель, чем отвечает. Одна модель в обеих ролях
                склонна признавать собственную работу верной, и доля отбраковок тогда
                говорит о согласии модели с собой, а не о качестве ответов.
              </p>
              <div className="mt-4">
                <ModelPicker
                  label="Модель"
                  hint="Пусто — судить той же моделью, что отвечает за персон."
                  value={draft.models.judge}
                  onChange={(id) => patch({ models: { ...draft.models, judge: id } })}
                  info={provider}
                  kind="text"
                  fallback={draft.models.text || provider?.current.text || ""}
                />
              </div>
            </section>

            <section className="rounded-lg border border-hairline bg-card p-6">
              <h2 className="text-sm font-semibold">Рассуждение судьи</h2>
              <p className="mt-1 text-xs leading-relaxed text-slate">
                Отдельно от основной модели: у проверки другая цена ошибки. Пропущенный
                дефект стоит одного странного ответа в отчёте, ложное срабатывание —
                выброшенного ответа, за который уже заплачено.
              </p>
              <div className="mt-4">
                <ReasoningControls
                  value={draft.judgeReasoning}
                  onChange={(judgeReasoning) => patch({ judgeReasoning })}
                />
              </div>
            </section>

            <section className="rounded-lg border border-hairline bg-card p-6">
              <h2 className="text-sm font-semibold">Температура</h2>
              <p className="mt-1 text-xs leading-relaxed text-slate">
                Задаётся в разделе «Настройки» вместе с остальными стадиями — здесь
                показана, чтобы было видно, с чем судья работает. Сейчас{" "}
                <span className="font-medium tabular-nums">{judgeTemperature.toFixed(1)}</span>.{" "}
                {TEMPERATURE_STAGES.find((s) => s.key === "answerJudge")?.hint}
              </p>
            </section>

            <div className="flex items-center gap-4">
              <button
                onClick={submit}
                disabled={!dirty || save.kind === "saving"}
                className="inline-flex items-center gap-2 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40"
              >
                {save.kind === "saving" && <Loader2 className="h-4 w-4 animate-spin" />}
                Сохранить
              </button>
              {save.kind === "ok" && (
                <span className="inline-flex items-center gap-1.5 text-sm text-success">
                  <Check className="h-4 w-4" />
                  Сохранено
                </span>
              )}
              {save.kind === "error" && (
                <span className="inline-flex items-center gap-1.5 text-sm text-danger">
                  <AlertCircle className="h-4 w-4" />
                  {save.message}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
