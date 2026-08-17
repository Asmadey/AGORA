"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ExternalLink, Info, X } from "lucide-react";

import { PersonaDnaView } from "@/components/agora/PersonaDnaView";

/**
 * «О персоне» — кто именно дал этот ответ, не уходя с отчёта.
 *
 * ─── Почему попап, а не ссылка ─────────────────────────────────────────────
 * Вопрос «а кто это сказал?» возникает ровно в момент чтения ответа, и
 * возникает много раз подряд: читатель сравнивает реакции разных персон. Ссылка
 * на отдельную страницу отвечала на него ценой ухода с отчёта и потери места в
 * списке — а место это, при десятках ответов, восстанавливается прокруткой.
 *
 * Прежняя ссылка «Карточка персоны» лежала ВНУТРИ раскрытого ответа, то есть
 * увидеть её можно было, только раскрыв ответ. Кнопка стоит рядом с именем и
 * доступна из свёрнутой строки — там, где вопрос и задают.
 *
 * ─── Почему загрузка по требованию ─────────────────────────────────────────
 * DNA персоны — это полсотни полей, и в отчёте таких персон дюжина. Приложить
 * их все к странице значило бы утроить её вес ради данных, которые обычно
 * никто не открывает. Запрос уходит при первом открытии и кешируется в
 * состоянии: второе открытие той же персоны бесплатно.
 */

interface PersonaPayload {
  id: string;
  name: string;
  dna: Record<string, unknown>;
  narrative: string | null;
  seed: number | null;
  createdAt: string;
}

export function PersonaDialog({
  personaId,
  personaName,
}: {
  personaId: string;
  personaName: string;
}) {
  const [open, setOpen] = useState(false);
  const [persona, setPersona] = useState<PersonaPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || persona) return;
    let alive = true;
    fetch(`/api/personas/${personaId}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`сервер ответил ${r.status}`);
        return (await r.json()) as { persona: PersonaPayload };
      })
      .then((payload) => alive && setPersona(payload.persona))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [open, persona, personaId]);

  // Escape закрывает: диалог перекрывает страницу целиком, и мышь до крестика
  // при прокрученном содержимом ещё надо довести.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex shrink-0 items-center gap-1 rounded-md border border-hairline px-2 py-1 text-xs text-slate transition-colors hover:border-hairline-strong hover:text-foreground"
      >
        <Info className="h-3.5 w-3.5" />
        О персоне
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          onClick={() => setOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label={`О персоне ${personaName}`}
        >
          <div
            className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-hairline bg-background p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold">{persona?.name ?? personaName}</h2>
                {persona && (
                  <p className="mt-0.5 text-xs text-slate">
                    Создана {new Date(persona.createdAt).toLocaleDateString("ru-RU")}
                    {persona.seed !== null && ` · seed ${persona.seed}`}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="shrink-0 rounded-md p-1 text-slate transition-colors hover:bg-secondary hover:text-foreground"
                aria-label="Закрыть"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {error ? (
              <p className="text-sm text-slate">Персона не загрузилась: {error}</p>
            ) : !persona ? (
              <p className="text-sm text-slate">Загружаем персону…</p>
            ) : (
              <PersonaDnaView dna={persona.dna} narrative={persona.narrative} columns={1} />
            )}

            <Link
              href={`/personas/${personaId}`}
              className="mt-5 inline-flex items-center gap-1.5 text-sm text-slate underline-offset-4 transition-colors hover:text-foreground hover:underline"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Открыть полную карточку
            </Link>
          </div>
        </div>
      )}
    </>
  );
}
