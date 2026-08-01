"use client";

import { useCallback, useEffect, useState } from "react";
import { RotateCcw, Save, Eye, AlertCircle, CheckCircle2, Clock } from "lucide-react";

interface PromptVersion {
  id: string;
  tenant_id: string | null;
  key: string;
  stage: string;
  template: string;
  variables: string[];
  model_params: Record<string, unknown>;
  version: number;
  is_active: boolean;
  is_default: boolean;
  created_at: string;
}

interface Props {
  promptKey: string;
  stage: string;
  desc: string;
  initialActive: PromptVersion | null;
  initialHistory: PromptVersion[];
}

/**
 * Клиентский редактор промпта (задача #26).
 *
 * Правка — действие owner, но компонент не проверяет роль: API сам вернёт 403
 * для member. Компонент показывает ошибки от API, а не дублирует гвард.
 *
 * Переменные извлекаются из шаблона в реальном времени (живая валидация):
 * множество {{плейсхолдеров}} в тексте подсвечивается, а несоответствие с
 * массивом variables (бывшим при сохранении) показывается сразу.
 */
export function PromptEditor({ promptKey, stage, desc, initialActive, initialHistory }: Props) {
  const [active, setActive] = useState<PromptVersion | null>(initialActive);
  const [history, setHistory] = useState<PromptVersion[]>(initialHistory);
  const [draft, setDraft] = useState<string>(initialActive?.template ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewValues, setPreviewValues] = useState<Record<string, string>>({});
  const [previewing, setPreviewing] = useState(false);

  // Переменные в текущем драфте
  const draftVars = (() => {
    const found = draft.matchAll(/\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g);
    return [...new Set([...found].map((m) => m[1]))];
  })();

  const isDirty = draft !== (active?.template ?? "");
  const isOwnerVersion = active && !active.is_default;
  const canRestore = history.some((h) => !h.is_default);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch("/api/prompts", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: promptKey, template: draft }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "ошибка сохранения");
      } else {
        setSuccess("версия сохранена и активирована");
        // Обновляем состояние
        const newPrompt = data.prompt as PromptVersion;
        setActive(newPrompt);
        setDraft(newPrompt.template);
        // Перезагружаем историю
        const histRes = await fetch(`/api/prompts/${encodeURIComponent(promptKey)}`);
        if (histRes.ok) {
          const histData = await histRes.json();
          setHistory(histData.history ?? []);
        }
      }
    } catch {
      setError("нет соединения с сервером");
    } finally {
      setSaving(false);
    }
  }, [draft, promptKey]);

  const handleActivate = useCallback(async (version: number) => {
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`/api/prompts/${encodeURIComponent(promptKey)}/activate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "ошибка активации");
      } else {
        setSuccess(`активирована версия ${version}`);
        const newPrompt = data.prompt as PromptVersion;
        setActive(newPrompt);
        setDraft(newPrompt.template);
        // Перезагружаем историю
        const histRes = await fetch(`/api/prompts/${encodeURIComponent(promptKey)}`);
        if (histRes.ok) {
          const histData = await histRes.json();
          setHistory(histData.history ?? []);
        }
      }
    } catch {
      setError("нет соединения с сервером");
    }
  }, [promptKey]);

  const handleRestore = useCallback(async () => {
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`/api/prompts/${encodeURIComponent(promptKey)}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "ошибка восстановления");
      } else {
        setSuccess("дефолт восстановлен");
        // Перезагружаем
        const histRes = await fetch(`/api/prompts/${encodeURIComponent(promptKey)}`);
        if (histRes.ok) {
          const histData = await histRes.json();
          setActive(histData.active);
          setHistory(histData.history ?? []);
          setDraft(histData.active?.template ?? "");
        }
      }
    } catch {
      setError("нет соединения с сервером");
    }
  }, [promptKey]);

  const handlePreview = useCallback(async () => {
    setPreviewing(true);
    setError(null);
    setPreviewText(null);
    try {
      const res = await fetch(`/api/prompts/${encodeURIComponent(promptKey)}/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values: previewValues }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "ошибка предпросмотра");
      } else {
        setPreviewText(data.text);
      }
    } catch {
      setError("нет соединения с сервером");
    } finally {
      setPreviewing(false);
    }
  }, [promptKey, previewValues]);

  // Сбрасываем драфт при смене активной версии
  useEffect(() => {
    if (active) setDraft(active.template);
  }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6">
      {/* Чипы состояния */}
      <div className="flex flex-wrap gap-2">
        <span className="inline-flex items-center rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground">
          стадия: {stage}
        </span>
        {active && (
          <>
            <span className="inline-flex items-center rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground">
              активная версия: {active.version}
            </span>
            {active.is_default ? (
              <span className="inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-xs">
                дефолт
              </span>
            ) : (
              <span className="inline-flex items-center rounded-full bg-foreground px-2.5 py-0.5 text-xs text-background">
                своя версия
              </span>
            )}
          </>
        )}
      </div>

      {error && (
        <p className="flex gap-2 rounded-md border border-rose-500/25 bg-rose-500/5 p-3 text-xs leading-relaxed text-rose-200/80">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      )}
      {success && (
        <p className="flex gap-2 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3 text-xs leading-relaxed text-emerald-200/80">
          <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {success}
        </p>
      )}

      {/* Переменные */}
      <section>
        <h2 className="text-sm font-semibold">Переменные в шаблоне</h2>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          {desc}. Переменные извлекаются из шаблона автоматически.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {draftVars.length === 0 ? (
            <span className="text-sm text-muted-foreground">
              Плейсхолдеров нет — шаблон статический.
            </span>
          ) : (
            draftVars.map((v) => (
              <code
                key={v}
                className="rounded border border-sky-500/30 bg-sky-500/10 px-2 py-1 font-mono text-xs text-sky-200"
              >
                {v}
              </code>
            ))
          )}
        </div>
      </section>

      {/* Редактор */}
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Редактор шаблона</h2>
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving || !isDirty}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs transition-colors hover:bg-secondary disabled:opacity-40"
            >
              <Save className="h-3.5 w-3.5" />
              {saving ? "сохранение…" : "сохранить новую версию"}
            </button>
            {canRestore && (
              <button
                onClick={handleRestore}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs transition-colors hover:bg-secondary"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                вернуть дефолт
              </button>
            )}
          </div>
        </div>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="h-96 w-full resize-y rounded-md border border-border bg-[hsl(222_47%_7%)] p-4 font-mono text-[13px] leading-relaxed focus:outline-none focus:ring-1 focus:ring-sky-500/50"
          spellCheck={false}
        />
        {isDirty && (
          <p className="mt-1 text-xs text-amber-200/70">
            есть несохранённые изменения
          </p>
        )}
      </section>

      {/* Предпросмотр */}
      <section>
        <h2 className="text-sm font-semibold">Предпросмотр (dry-run)</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Подстановка тестовых значений без вызова модели. Заполните все переменные.
        </p>
        <div className="mt-3 space-y-2">
          {draftVars.map((v) => (
            <div key={v} className="flex items-center gap-2">
              <code className="w-48 shrink-0 font-mono text-xs text-sky-200">{`{{${v}}}`}</code>
              <input
                type="text"
                value={previewValues[v] ?? ""}
                onChange={(e) =>
                  setPreviewValues((prev) => ({ ...prev, [v]: e.target.value }))
                }
                placeholder={`значение для ${v}`}
                className="flex-1 rounded border border-border bg-[hsl(222_47%_7%)] px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-sky-500/50"
              />
            </div>
          ))}
        </div>
        <button
          onClick={handlePreview}
          disabled={previewing || draftVars.length === 0}
          className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs transition-colors hover:bg-secondary disabled:opacity-40"
        >
          <Eye className="h-3.5 w-3.5" />
          {previewing ? "подстановка…" : "предпросмотр"}
        </button>
        {previewText && (
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-md border border-border bg-[hsl(222_47%_7%)] p-4 font-mono text-[13px] leading-relaxed">
            {previewText}
          </pre>
        )}
      </section>

      {/* История версий */}
      <section>
        <h2 className="text-sm font-semibold">История версий</h2>
        <div className="mt-2 divide-y divide-border overflow-hidden rounded-lg border border-border">
          {history.map((v) => (
            <div
              key={v.id}
              className="flex items-center gap-4 bg-[hsl(222_47%_7%)] px-5 py-3"
            >
              <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <span className="font-mono text-sm">v{v.version}</span>
                <span className="ml-3 text-xs text-muted-foreground">
                  {new Date(v.created_at).toLocaleString("ru-RU")}
                </span>
              </div>
              {v.is_active && (
                <span className="inline-flex items-center rounded-full bg-foreground px-2.5 py-0.5 text-xs text-background">
                  активна
                </span>
              )}
              {v.is_default && (
                <span className="inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-xs">
                  дефолт
                </span>
              )}
              {!v.is_active && !v.is_default && (
                <button
                  onClick={() => handleActivate(v.version)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1 text-xs transition-colors hover:bg-secondary"
                >
                  сделать активной
                </button>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}