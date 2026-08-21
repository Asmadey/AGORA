"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";
import { REASONING_EFFORTS, type Reasoning, type ReasoningEffort } from "@/lib/settings";

/**
 * Выбор модели и режима рассуждения — общий для Настроек и раздела «QA судья».
 *
 * Написанные порознь, два экрана разошлись бы: сначала подписями, потом
 * составом списка, — а список у них один и тот же, живой, от провайдера.
 */

export interface ProviderModel {
  id: string;
  vision: boolean;
}

export interface ProviderInfo {
  current: { endpoint: string; keyMask: string; text: string; vision: string };
  models: ProviderModel[];
  guessed?: boolean;
  error?: string | null;
}

/** Одна загрузка списка на страницу: он одинаков для всех селекторов. */
export function useProviderModels(): ProviderInfo | null {
  const [info, setInfo] = useState<ProviderInfo | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/models")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => alive && d && setInfo(d as ProviderInfo))
      .catch(() => {
        if (!alive) return;
        // Недоступность списка не должна оставлять экран пустым: остальные
        // поля работают, а модель можно вписать руками.
        setInfo({
          current: { endpoint: "", keyMask: "неизвестен", text: "", vision: "" },
          models: [],
          error: "список моделей не загрузился",
        });
      });
    return () => {
      alive = false;
    };
  }, []);

  return info;
}

export function ModelPicker({
  label,
  hint,
  value,
  onChange,
  info,
  kind,
  fallback,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (id: string) => void;
  info: ProviderInfo | null;
  /** Какие модели показывать: зрение или текст. */
  kind: "text" | "vision";
  /** Что действует, когда выбор пуст, — значение из окружения сервера. */
  fallback: string;
}) {
  const models = (info?.models ?? []).filter((m) => (kind === "vision" ? m.vision : !m.vision));

  return (
    <div>
      <label className="block text-sm font-medium">{label}</label>
      <p className="mt-1 text-xs leading-relaxed text-slate">{hint}</p>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-2 w-full rounded-md border border-hairline bg-background px-3 py-2 font-mono text-sm"
      >
        {/* Пустое значение — законный выбор, а не «ничего не выбрано»: оно
            означает «как задано в окружении сервера», и именно так работают
            все прогоны до первого захода в настройки. */}
        <option value="">
          как в окружении{fallback ? ` (${fallback})` : ""}
        </option>
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.id}
          </option>
        ))}
        {/* Ранее выбранная модель могла исчезнуть из списка провайдера.
            Показываем её отдельно, иначе select молча сбросит выбор на
            умолчание, и прогон пойдёт по другой модели без единого следа. */}
        {value && !models.some((m) => m.id === value) && (
          <option value={value}>{value} — нет в списке провайдера</option>
        )}
      </select>
    </div>
  );
}

export function ReasoningControls({
  value,
  onChange,
}: {
  value: Reasoning;
  onChange: (next: Reasoning) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={value.thinking}
            onChange={(e) => onChange({ ...value, thinking: e.target.checked })}
            className="h-4 w-4 accent-foreground"
          />
          <span className="text-sm">Размышление перед ответом</span>
        </label>
        <p className="mt-1 text-xs leading-relaxed text-slate">
          Уезжает ключом <code className="font-mono">enable_thinking</code>. Замер на
          боевом ключе: с выключенным размышлением ответ занимает 4 токена вместо
          289 — разница в семьдесят раз. Ключ{" "}
          <code className="font-mono">thinking</code> из документации провайдера этот
          шлюз игнорирует, поэтому переключатель повешен на первый.
        </p>
      </div>

      <div>
        <p className="text-sm">Усилия рассуждения</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {REASONING_EFFORTS.map((effort) => (
            <button
              key={effort}
              type="button"
              onClick={() => onChange({ ...value, effort: effort as ReasoningEffort })}
              className={cn(
                "rounded-md border px-3 py-1.5 text-sm transition-colors",
                value.effort === effort
                  ? "border-ink bg-secondary"
                  : "border-hairline hover:bg-secondary",
              )}
            >
              {effort}
            </button>
          ))}
        </div>
        {/* Честная подпись вместо молчания: ручка, которая ничего не крутит и
            об этом не сообщает, хуже отсутствующей — по ней принимают решения. */}
        <p className="mt-1 text-xs leading-relaxed text-warning">
          Текущий endpoint этот параметр игнорирует: замер показал одинаковый
          результат при <code className="font-mono">max</code> и без параметра вовсе.
          Значение сохраняется и отправляется — заработает при смене провайдера.
        </p>
      </div>
    </div>
  );
}
