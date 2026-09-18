"use client";

import { useState } from "react";
import { useCallback, useEffect } from "react";
import { Share2, Copy, Check, ShieldAlert } from "lucide-react";

/**
 * Диалог публичной ссылки (#29).
 *
 * Интерфейс намеренно проговаривает последствия: ссылка работает БЕЗ логина, то есть
 * это единственный санкционированный обход изоляции арендатора. Пользователь должен
 * понимать это до нажатия, а не узнавать постфактум. Поэтому TTL обязателен и
 * выбирается явно, а не прячется в умолчаниях.
 */

import { TTL_OPTIONS, type ActiveShare, type Ttl } from "@/lib/share";

const scopeLabels = {
  full: "Весь отчёт",
  aggregate: "Только сводка",
} as const;

function dateLabel(value: string | null): string {
  if (!value) return "бессрочно";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function ShareDialog({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false);
  const [ttl, setTtl] = useState<Ttl>("7d");
  const [scope, setScope] = useState<"full" | "aggregate">("full");
  const [link, setLink] = useState<string | null>(null);
  const [activeLinks, setActiveLinks] = useState<ActiveShare[]>([]);
  const [loadingLinks, setLoadingLinks] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLinks = useCallback(async () => {
    setLoadingLinks(true);
    try {
      const res = await fetch(`/api/tasks/${runId}/share`);
      const data = (await res.json()) as { active?: ActiveShare[]; error?: string };
      if (!res.ok) {
        setError(data.error ?? "не удалось загрузить список ссылок");
        return;
      }
      setActiveLinks(data.active ?? []);
    } catch {
      setError("не удалось загрузить список ссылок");
    } finally {
      setLoadingLinks(false);
    }
  }, [runId]);

  useEffect(() => {
    if (open) void loadLinks();
  }, [loadLinks, open]);

  const close = () => {
    // Адрес существует только в памяти после выпуска. После закрытия его
    // намеренно нельзя снова получить из списка: потерянную ссылку выпускают заново.
    setOpen(false);
    setLink(null);
    setCopied(false);
    setError(null);
  };

  /**
   * Ссылку выпускает СЕРВЕР.
   *
   * Прежде токен собирался здесь четырьмя вызовами Math.random и подставлялся в
   * адрес несуществующего домена. `Math.random` не криптографический — для
   * ссылки, открывающей отчёт без входа в систему, это то же самое, что
   * открытый доступ; а домена agora.studio у продукта нет вовсе.
   */
  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/tasks/${runId}/share`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ttl, scope }),
      });
      const data = (await res.json()) as { url?: string; error?: string };
      if (!res.ok || !data.url) {
        setError(data.error ?? "не удалось выпустить ссылку");
        return;
      }
      setLink(data.url);
      setCopied(false);
      await loadLinks();
    } catch {
      setError("сервер не ответил");
    } finally {
      setBusy(false);
    }
  };

  /** Отзыв: адрес перестаёт открываться сразу, проверку делает политика в базе. */
  const revokeOne = async (shareId: string) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/tasks/${runId}/share?shareId=${encodeURIComponent(shareId)}`,
        { method: "DELETE" },
      );
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        setError(data.error ?? "не удалось отозвать ссылку");
        return;
      }
      setLink(null);
      await loadLinks();
    } catch {
      setError("сервер не ответил");
    } finally {
      setBusy(false);
    }
  };

  const revokeAll = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/tasks/${runId}/share`, { method: "DELETE" });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        setError(data.error ?? "не удалось отозвать ссылки");
        return;
      }
      setLink(null);
      await loadLinks();
    } catch {
      setError("сервер не ответил");
    } finally {
      setBusy(false);
    }
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
        className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
      >
        <Share2 className="h-4 w-4" />
        Поделиться
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          onClick={close}
        >
          <div
            className="w-full max-w-md rounded-lg border border-hairline bg-card p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold">Публичная ссылка на отчёт</h2>

            {/*
              Текст обёрнут в span, а не лежит в flex-контейнере голым.
              Голый текст внутри flex становится анонимным flex-элементом, и
              каждый его кусок, разорванный тегом <strong>, — отдельным: строка
              разъезжалась на три колонки вместо одного абзаца.
            */}
            <p className="mt-3 flex gap-2.5 rounded-md border border-warning/30 bg-warning-soft/60 p-3 text-xs leading-relaxed text-warning">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                По ссылке отчёт открывается <strong>без входа в систему</strong>. Любой,
                у кого она есть, увидит содержимое. Ссылку можно отозвать в любой момент.
              </span>
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
                      scope === o.v ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary"
                    }`}
                  >
                    <span className="block font-medium">{o.t}</span>
                    <span className="mt-0.5 block text-xs text-slate">{o.d}</span>
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
                      ttl === o.value ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary"
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            {link && (
              <div className="mt-5">
                <div className="flex items-center gap-2 rounded-md border border-hairline bg-background px-3 py-2">
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">{link}</span>
                  <button
                    onClick={copy}
                    className="shrink-0 text-slate transition-colors hover:text-foreground"
                    aria-label="Скопировать"
                  >
                    {copied ? (
                      <Check className="h-4 w-4 text-success" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </button>
                </div>
                <p className="mt-2 text-xs text-slate">
                  Действует {TTL_OPTIONS.find((o) => o.value === ttl)?.label.toLowerCase()}.
                  Просмотры записываются в журнал. Ссылка показывается один раз: в базе
                  хранится только её отпечаток, и восстановить адрес нельзя — потерянную
                  выпускают заново.
                </p>
              </div>
            )}

            <button
              onClick={create}
              disabled={busy}
              className="mt-6 w-full rounded-md bg-foreground py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {busy ? "Выпускаю…" : link ? "Создать ещё ссылку" : "Создать ссылку"}
            </button>

            <section className="mt-6" aria-label="active-share-list">
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="text-sm font-medium">Действующие ссылки</h3>
                <span className="text-xs text-slate">{activeLinks.length}</span>
              </div>

              {loadingLinks ? (
                <p className="mt-3 text-xs text-slate">Загружаю список…</p>
              ) : activeLinks.length === 0 ? (
                <p className="mt-3 text-xs text-slate">Действующих ссылок пока нет.</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {activeLinks.map((share) => (
                    <li
                      key={share.id}
                      className="rounded-md border border-hairline bg-background p-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 text-xs">
                          <p className="font-medium">{scopeLabels[share.scope]}</p>
                          <p className="mt-1 text-slate">
                            Выпущена {dateLabel(share.createdAt)}
                          </p>
                          <p className="mt-0.5 text-slate">
                            До {dateLabel(share.expiresAt)} · Просмотров: {share.viewCount}
                          </p>
                        </div>
                        <button
                          onClick={() => void revokeOne(share.id)}
                          disabled={busy}
                          className="shrink-0 text-xs text-danger transition-colors hover:underline disabled:opacity-50"
                        >
                          Отозвать
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              {activeLinks.length > 0 && (
                <button
                  onClick={() => void revokeAll()}
                  disabled={busy}
                  className="mt-3 w-full rounded-md border border-danger/40 py-2 text-sm text-danger transition-colors hover:bg-danger/5 disabled:opacity-50"
                >
                  Отозвать все ссылки
                </button>
              )}
            </section>

            {error && (
              <p className="mt-3 rounded-md border border-danger/40 bg-danger/5 p-2.5 text-xs text-danger">
                {error}
              </p>
            )}

            <button
              onClick={close}
              className="mt-3 w-full rounded-md border border-hairline py-2 text-sm transition-colors hover:bg-secondary"
            >
              Закрыть
            </button>
          </div>
        </div>
      )}
    </>
  );
}
