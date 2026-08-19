"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, MessageCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { CRITERIA, CRITERIA_LABELS } from "@/lib/agora-types";
import { answerForQuestion, retentionShort } from "@/lib/report-view";
import type { AnswerView, AskedQuestion } from "@/lib/report-view";
import { PersonaDialog } from "./PersonaDialog";
import { TimecodeRef } from "./Primitives";

/**
 * Аккордеон по персонам (PRD §5.E, §6).
 *
 * Свёрнутая строка показывает то, по чему принимают решение: балл и намерение
 * досмотреть. Развёрнутая — обоснование с таймкодами. Смысл в том, чтобы
 * средний балл всегда можно было раскрыть до конкретной реплики конкретной
 * персоны — иначе агрегат ничем не отличается от догадки.
 *
 * Компонент получает разобранные карточки отчёта, а не персон из реестра.
 * Персону могли отредактировать или удалить после прогона, а отчёт обязан
 * показывать ту аудиторию, на которой посчитан.
 *
 * Ключ строки — персона И номер повтора: при перекрытии ×3 одна персона даёт
 * три карточки, и ключ по одному persona_id схлопнул бы их в одну строку.
 */
/**
 * Вопросы, ответ на которые промпт велит класть в структурный блок
 * `perception`, а не в `survey_answers`.
 *
 * Тот же список, что в правиле покрытия воркера (`qa/checks.py`). Без него
 * карточка показывала бы «не ответила» на вопрос, на который персона ответила
 * ровно туда, куда её просили, — и читатель винил бы персону вместо разметки.
 */
/** Подписи свободных ответов. Ключ без подписи показывается как есть. */
const VERBATIM_LABELS: Record<string, string> = {
  why_impression: "Почему такое впечатление",
  memorable_elements: "Что запомнилось",
  character_opinions: "О героях",
};

export function PersonaAccordion({
  answers,
  runId,
  asked = [],
}: {
  answers: AnswerView[];
  runId: string;
  /**
   * Вопросы прогона в том порядке, в каком их задали. Берутся из снимка
   * `survey_asked`, а не из анкеты на момент чтения отчёта: анкету правят между
   * прогонами, и показать сегодняшние вопросы под вчерашними ответами значило
   * бы соврать о том, что персону спрашивали.
   */
  asked?: AskedQuestion[];
}) {
  const [openKey, setOpenKey] = useState<string | null>(null);

  if (answers.length === 0) {
    return (
      <p className="rounded-lg border border-hairline p-5 text-sm text-slate">
        Ответов нет. Если прогон завершён, смотрите причины на экране прогресса —
        пустой отчёт при успешном прогоне означает, что все ответы забракованы QA.
      </p>
    );
  }

  return (
    <div className="divide-y divide-border overflow-hidden rounded-lg border border-hairline">
      {answers.map((a) => {
        const key = `${a.personaId}#${a.replication}`;
        const open = openKey === key;

        return (
          <div key={key} className="bg-card">
            {/*
              Строка — контейнер, а не одна кнопка: «О персоне» стоит рядом с
              именем, а кнопка внутри кнопки — невалидная разметка, которую
              браузеры чинят каждый по-своему. Поэтому раскрытие повешено на два
              явных элемента: блок с именем слева и шеврон справа.
            */}
            {/*
              Раскрытие по ВСЕЙ площади строки.

              Прежде строка была обычным div с подсветкой при наведении и без
              обработчика: раскрывали её две кнопки — блок с именем и шеврон.
              Подсветка обманывала, обещая клик, которого не было.

              Обработчик стоит здесь ОДИН. Оставить его ещё и на блоке с именем
              значило бы получить двойное срабатывание: клик по имени раскрыл бы
              и тут же свернул — выглядит как «кнопка не работает».

              role/tabIndex/onKeyDown обязательны: раскрытие было доступно с
              клавиатуры, пока висело на кнопках, и потерять это молча нельзя.
            */}
            <div
              role="button"
              tabIndex={0}
              aria-expanded={open}
              onClick={() => setOpenKey(open ? null : key)}
              onKeyDown={(e) => {
                if (e.key !== "Enter" && e.key !== " ") return;
                // Пробел на кнопке иначе прокручивает страницу — стандартное
                // поведение документа, которое здесь мешает.
                e.preventDefault();
                setOpenKey(open ? null : key);
              }}
              className="flex w-full cursor-pointer items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-secondary/40"
            >
              {/* Обычный div: обработчик теперь на всей строке, и второй здесь
                  дал бы двойное срабатывание. */}
              <div className="flex min-w-0 items-center gap-4 text-left">
                <div
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs font-semibold"
                  style={{
                    backgroundColor: `hsl(${a.avatarHue} 45% 22%)`,
                    color: `hsl(${a.avatarHue} 70% 78%)`,
                  }}
                >
                  {a.initials}
                </div>

                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {a.personaName}
                    {a.replication > 0 && (
                      <span className="ml-2 text-xs text-slate">
                        повтор {a.replication + 1}
                      </span>
                    )}
                  </p>
                  <p className="truncate text-xs text-slate">
                    {a.segmentLabel ?? "срез не записан"}
                  </p>
                </div>
              </div>

              <PersonaDialog personaId={a.personaId} personaName={a.personaName} />

              {/* Распорка: всё, что правее, прижато к краю строки. */}
              <div className="flex-1" />

              {a.qaFlags.length > 0 && (
                <span
                  title={`QA: ${a.qaFlags.join("; ")}`}
                  className="hidden items-center gap-1 text-xs text-amber-400 sm:inline-flex"
                >
                  <AlertTriangle className="h-3.5 w-3.5" />
                  QA
                </span>
              )}

              {/*
                Две колонки, а не одна. Прежде здесь стояло одно поле: процент
                доли просмотра, если он есть, иначе категория словами. Это два
                РАЗНЫХ вопроса анкеты, и в одной колонке они читались как
                «часть персон отвечает в процентах, часть словами» — именно так
                это и увидел владелец.
              */}
              <div className="hidden w-24 shrink-0 text-right sm:block">
                <p className="text-xs text-slate">Досмотрит</p>
                <p className="truncate text-sm" title={a.retentionIntent ?? undefined}>
                  {retentionShort(a.retentionIntent)}
                </p>
              </div>

              <div className="hidden w-16 shrink-0 text-right sm:block">
                <p className="text-xs text-slate">Доля</p>
                <p className="text-sm tabular-nums">
                  {a.watchedShare !== null ? `${a.watchedShare}%` : "—"}
                </p>
              </div>

              <div className="w-14 shrink-0 text-right">
                <p
                  className={cn(
                    "text-xl font-semibold tabular-nums",
                    a.overall === null
                      ? "text-slate"
                      : a.overall >= 8
                        ? "text-success"
                        : a.overall >= 6.5
                          ? ""
                          : "text-amber-400",
                  )}
                >
                  {a.overall === null ? "—" : a.overall.toFixed(1)}
                </p>
              </div>

              {/* Индикатор, а не кнопка: раскрывает вся строка. Кнопка здесь
                  ловила бы тот же клик вторым обработчиком. */}
              <span className="shrink-0 p-1 text-slate" aria-hidden="true">
                <ChevronDown
                  className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
                />
              </span>
            </div>

            {open && (
              <div className="border-t border-hairline/60 px-5 py-5">
                <div className="grid gap-4 sm:grid-cols-5">
                  {CRITERIA.map((c) => (
                    <div key={c}>
                      <p className="text-xs text-slate">{CRITERIA_LABELS[c]}</p>
                      <p className="mt-0.5 text-lg font-semibold tabular-nums">
                        {a.scores[c] ?? "—"}
                      </p>
                    </div>
                  ))}
                </div>

                {/*
                  Ответы на анкету. Прежде их не было вовсе: карточка
                  показывала пять баллов, одну цитату и таймкоды, а на что
                  персона отвечала — нет. Вопрос «Как дела?», заданный сверх
                  базовых, не появлялся нигде, и выглядело это так, будто
                  персона его проигнорировала.

                  Обход идёт по ЗАДАННЫМ вопросам, а не по ответам: вопрос без
                  ответа обязан быть виден, иначе пропуск неотличим от того,
                  что вопроса не было.
                */}
                {asked.length > 0 && (
                  <div className="mt-5">
                    <h3 className="text-xs uppercase tracking-wide text-slate">
                      Ответы на анкету
                    </h3>
                    <dl className="mt-2 space-y-2 text-sm">
                      {asked.map((q) => {
                        const value = answerForQuestion(a, q);
                        return (
                          <div key={q.id} className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                            <dt className="text-slate">{q.label}</dt>
                            <dd className={value ? "" : "text-slate/60"}>
                              {value ?? "— не ответила"}
                            </dd>
                          </div>
                        );
                      })}
                    </dl>
                  </div>
                )}

                {/* Свободные ответы: их несколько, и в свёрнутой строке место
                    было только под первый. */}
                {Object.keys(a.verbatims).length > 0 ? (
                  <div className="mt-5 space-y-3">
                    {Object.entries(a.verbatims).map(([key, text]) => (
                      <blockquote
                        key={key}
                        className="border-l-2 border-hairline pl-4 text-sm leading-relaxed"
                      >
                        <span className="block text-xs text-slate">{VERBATIM_LABELS[key] ?? key}</span>
                        «{text}»
                      </blockquote>
                    ))}
                  </div>
                ) : (
                  a.verbatim && (
                    <blockquote className="mt-5 border-l-2 border-hairline pl-4 text-sm leading-relaxed">
                      «{a.verbatim}»
                    </blockquote>
                  )
                )}

                {a.groundingRefs.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {a.groundingRefs.map((r) => (
                      <TimecodeRef key={`${r.timecode}${r.note}`} timecode={r.timecode} note={r.note} />
                    ))}
                  </div>
                )}

                {a.qaFlags.length > 0 && (
                  <ul className="mt-4 space-y-1 text-xs text-amber-400">
                    {a.qaFlags.map((f) => (
                      <li key={f}>— {f}</li>
                    ))}
                  </ul>
                )}

                <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate">
                  {a.nps !== null && <span>Порекомендует: {a.nps} из 10</span>}
                  {a.emotions.length > 0 && <span>Эмоции: {a.emotions.join(", ")}</span>}
                  {/* Ссылки «Карточка персоны» здесь больше нет: она лежала
                      внутри раскрытого ответа, то есть увидеть её можно было,
                      только раскрыв ответ. Вопрос «кто это сказал» задают
                      раньше — кнопка «О персоне» стоит в свёрнутой строке. */}
                  <Link
                    href={`/runs/${runId}/chat?persona=${a.personaId}`}
                    className="inline-flex items-center gap-1.5 underline-offset-4 hover:text-foreground hover:underline"
                  >
                    <MessageCircle className="h-3.5 w-3.5" />
                    Спросить персону
                  </Link>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
