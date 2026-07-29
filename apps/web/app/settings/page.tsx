"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, AlertCircle } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { cn } from "@/lib/utils";
import {
  DEFAULT_SETTINGS,
  COST_CAP_BOUNDS,
  REPLICATION_VALUES,
  settingsEqual,
  type TenantSettings,
  type ReplicationCount,
} from "@/lib/settings";

/**
 * Настройки арендатора (задача #27, PRD §12).
 *
 * Три переключателя, каждый из которых напрямую влияет либо на стоимость прогона,
 * либо на его длительность. Поэтому рядом с каждым написано, чем именно платит
 * пользователь за выбор — иначе значения по умолчанию выбираются вслепую.
 *
 * Сохранение явное, а не автоматическое. Смена модели транскрипции меняет
 * поведение всех последующих прогонов команды; такое изменение должно быть
 * подтверждено нажатием, а не случайным кликом мимо. Пока изменения не сохранены,
 * это видно и уйти со страницы молча нельзя.
 */

type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "error"; message: string };

export default function SettingsPage() {
  const [saved, setSaved] = useState<TenantSettings>(DEFAULT_SETTINGS);
  const [draft, setDraft] = useState<TenantSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [save, setSave] = useState<SaveState>({ kind: "idle" });

  const dirty = !settingsEqual(saved, draft);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/settings")
      .then((r) => r.json())
      .then((data: { settings?: TenantSettings }) => {
        if (cancelled || !data.settings) return;
        setSaved(data.settings);
        setDraft(data.settings);
      })
      .catch(() => {
        /* остаёмся на значениях по умолчанию — они же показаны на экране */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Несохранённые правки легко потерять переходом по ссылке или закрытием вкладки.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const patch = (p: Partial<TenantSettings>) => {
    setDraft((d) => ({ ...d, ...p }));
    setSave({ kind: "idle" });
  };

  const submit = async () => {
    setSave({ kind: "saving" });
    try {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const data = await res.json();
      if (!res.ok) {
        setSave({
          kind: "error",
          message: Array.isArray(data.details) ? data.details.join("; ") : (data.error ?? "не удалось сохранить"),
        });
        return;
      }
      setSaved(data.settings);
      setDraft(data.settings);
      setSave({ kind: "saved" });
    } catch {
      setSave({ kind: "error", message: "сервер недоступен" });
    }
  };

  return (
    <>
      <PageHeader
        title="Настройки"
        subtitle="Применяются ко всем исследованиям команды. Значения можно переопределить при запуске конкретного прогона."
      />

      <div className="max-w-2xl space-y-4 p-8 pb-32">
        <section className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-6">
          <h2 className="text-sm font-semibold">Лимит вызовов модели</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Разбор кадров — самая дорогая стадия. Жёсткий лимит обрывает прогон при
            превышении: отчёт будет неполным, но счёт предсказуемым.
          </p>
          <div className="mt-4 flex gap-2">
            {(
              [
                { v: "auto", t: "Авто", d: "без потолка" },
                { v: "hard", t: "Жёсткий лимит", d: "оборвать при превышении" },
              ] as const
            ).map((o) => (
              <button
                key={o.v}
                onClick={() => patch({ costCap: o.v })}
                className={cn(
                  "flex-1 rounded-md border p-3 text-left transition-colors",
                  draft.costCap === o.v ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50",
                )}
              >
                <span className="block text-sm font-medium">{o.t}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">{o.d}</span>
              </button>
            ))}
          </div>
          {draft.costCap === "hard" && (
            <div className="mt-4 flex items-center gap-4">
              <input
                type="range"
                min={COST_CAP_BOUNDS.min}
                max={COST_CAP_BOUNDS.max}
                step={COST_CAP_BOUNDS.step}
                value={draft.costCapValue}
                onChange={(e) => patch({ costCapValue: Number(e.target.value) })}
                className="flex-1"
              />
              <span className="w-24 text-right text-sm tabular-nums">{draft.costCapValue} вызовов</span>
            </div>
          )}
        </section>

        <section className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-6">
          <h2 className="text-sm font-semibold">Модель транскрипции</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Транскрипция идёт на CPU. На длинных материалах large-v3 существенно
            медленнее, turbo быстрее при небольшой потере точности распознавания.
          </p>
          <div className="mt-4 flex gap-2">
            {(
              [
                { v: "large-v3", t: "large-v3", d: "точнее, медленнее" },
                { v: "large-v3-turbo", t: "large-v3-turbo", d: "быстрее, чуть менее точно" },
              ] as const
            ).map((o) => (
              <button
                key={o.v}
                onClick={() => patch({ whisperModel: o.v })}
                className={cn(
                  "flex-1 rounded-md border p-3 text-left transition-colors",
                  draft.whisperModel === o.v ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50",
                )}
              >
                <span className="block font-mono text-sm">{o.t}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">{o.d}</span>
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
            Выбор фиксируется в задаче на момент её создания и не меняется на лету:
            иначе прогон, начатый на одной модели, досчитался бы на другой, и отличить
            влияние модели от влияния материала стало бы невозможно.
          </p>
        </section>

        <section className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-6">
          <h2 className="text-sm font-semibold">Перекрытие по умолчанию</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Сколько раз каждая персона проходит анкету. Больше повторов — виден разброс
            и понятна устойчивость результата, но стоимость растёт пропорционально.
          </p>
          <div className="mt-4 flex gap-2">
            {REPLICATION_VALUES.map((n) => (
              <button
                key={n}
                onClick={() => patch({ defaultReplication: n as ReplicationCount })}
                className={cn(
                  "flex-1 rounded-md border py-2.5 text-sm transition-colors",
                  draft.defaultReplication === n
                    ? "border-foreground bg-secondary"
                    : "border-border hover:bg-secondary/50",
                )}
              >
                ×{n}
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-6">
          <h2 className="text-sm font-semibold">Провайдер моделей</h2>
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">Модель</dt>
              <dd className="font-mono">qwen3.6</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">Endpoint</dt>
              <dd className="font-mono text-xs">api.timeweb.cloud/v1</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">Ключ</dt>
              <dd className="text-muted-foreground">задан в окружении сервера</dd>
            </div>
          </dl>
          <p className="mt-4 text-xs text-muted-foreground">
            Ключи не хранятся в базе и не редактируются из интерфейса — только через
            переменные окружения.
          </p>
        </section>
      </div>

      {/* Панель сохранения. Прижата к низу рабочей области, чтобы кнопка не уезжала
          за пределы экрана на длинной странице. */}
      <div className="sticky bottom-0 border-t border-border bg-background/95 px-8 py-4 backdrop-blur">
        <div className="flex max-w-2xl items-center gap-4">
          <button
            onClick={submit}
            disabled={!dirty || save.kind === "saving" || loading}
            className="inline-flex items-center gap-2 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40"
          >
            {save.kind === "saving" && <Loader2 className="h-4 w-4 animate-spin" />}
            Сохранить
          </button>

          {dirty && (
            <button
              onClick={() => {
                setDraft(saved);
                setSave({ kind: "idle" });
              }}
              className="rounded-md border border-border px-4 py-2.5 text-sm transition-colors hover:bg-secondary"
            >
              Отменить
            </button>
          )}

          <span className="text-xs text-muted-foreground">
            {loading && "Загрузка…"}
            {!loading && dirty && "Есть несохранённые изменения"}
            {!loading && !dirty && save.kind === "saved" && (
              <span className="inline-flex items-center gap-1.5 text-emerald-400">
                <Check className="h-3.5 w-3.5" />
                Сохранено
              </span>
            )}
            {!loading && !dirty && save.kind !== "saved" && "Изменений нет"}
          </span>

          {save.kind === "error" && (
            <span className="inline-flex items-center gap-1.5 text-xs text-rose-300">
              <AlertCircle className="h-3.5 w-3.5" />
              {save.message}
            </span>
          )}
        </div>
      </div>
    </>
  );
}
