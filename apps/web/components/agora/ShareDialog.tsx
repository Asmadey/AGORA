"use client";

import { useState } from "react";
import { Share2, Copy, Check, ShieldAlert } from "lucide-react";

/**
 * Диалог публичной ссылки (#29).
 *
 * Интерфейс намеренно проговаривает последствия: ссылка работает БЕЗ логина, то есть
 * это единственный санкционированный обход изоляции арендатора. Пользователь должен
 * понимать это до нажатия, а не узнавать постфактум. Поэтому TTL обязателен и
 * выбирается явно, а не прячется в умолчаниях.
 */

const TTL_OPTIONS = [
  { value: "24h", label: "24 часа" },
  { value: "7d", label: "7 дней" },
  { value: "30d", label: "30 дней" },
] as const;

export function ShareDialog() {
  const [open, setOpen] = useState(false);
  const [ttl, setTtl] = useState<string>("7d");
  const [scope, setScope] = useState<"full" | "aggregate">("full");
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const create = () => {
    // Витрина: настоящий токен выпускает бэкенд и хранит только его SHA-256.
    const token = Array.from({ length: 4 }, () =>
      Math.random().toString(36).slice(2, 10),
    ).join("");
    setLink(`https://agora.studio/s/${token}`);
    setCopied(false);
  };

  const copy = async () => {
    if (!link) return;
    await navigator.clipboard.writeText(link);
    setCopied(true);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
      >
        <Share2 className="h-4 w-4" />
        Поделиться
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-lg border border-border bg-[hsl(222_47%_8%)] p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold">Публичная ссылка на отчёт</h2>

            <p className="mt-3 flex gap-2.5 rounded-md border border-amber-500/25 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-200/80">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
              По ссылке отчёт открывается <strong>без входа в систему</strong>. Любой, у
              кого она есть, увидит содержимое. Ссылку можно отозвать в любой момент.
            </p>

            <div className="mt-5">
              <p className="mb-2 text-sm">Что показывать</p>
              <div className="grid grid-cols-2 gap-2">
                {(
                  [
                    { v: "full", t: "Весь отчёт", d: "Включая имена персон" },
                    { v: "aggregate", t: "Только сводку", d: "Без данных персон" },
                  ] as const
                ).map((o) => (
                  <button
                    key={o.v}
                    onClick={() => setScope(o.v)}
                    className={`rounded-md border p-3 text-left text-sm transition-colors ${
                      scope === o.v ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50"
                    }`}
                  >
                    <span className="block font-medium">{o.t}</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">{o.d}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-5">
              <p className="mb-2 text-sm">Срок действия</p>
              <div className="flex gap-2">
                {TTL_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    onClick={() => setTtl(o.value)}
                    className={`flex-1 rounded-md border px-3 py-2 text-sm transition-colors ${
                      ttl === o.value ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50"
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            {link ? (
              <div className="mt-5">
                <div className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2">
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">{link}</span>
                  <button
                    onClick={copy}
                    className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                    aria-label="Скопировать"
                  >
                    {copied ? (
                      <Check className="h-4 w-4 text-emerald-400" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </button>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  Действует {TTL_OPTIONS.find((o) => o.value === ttl)?.label.toLowerCase()}.
                  Просмотры записываются в журнал.
                </p>
              </div>
            ) : (
              <button
                onClick={create}
                className="mt-6 w-full rounded-md bg-foreground py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90"
              >
                Создать ссылку
              </button>
            )}

            <button
              onClick={() => setOpen(false)}
              className="mt-3 w-full rounded-md border border-border py-2 text-sm transition-colors hover:bg-secondary"
            >
              Закрыть
            </button>
          </div>
        </div>
      )}
    </>
  );
}
