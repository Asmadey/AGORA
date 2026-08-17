"use client";

import { useEffect, useRef, useState } from "react";

import type { TimelineCell, TimelineView } from "@/lib/server/content-pack";

/**
 * Плеер и таймлайн материала: слева ролик, справа сцены по 5–30 секунд.
 *
 * ─── Зачем это на экране исследования ──────────────────────────────────────
 * Персона видит не ролик, а его разбор: описания сцен с таймкодами и реплики.
 * Всё, чего в разборе нет, для неё не существует, и QA сверяет ответы именно с
 * ним. Пока разбор не показан, читатель отчёта не может проверить ни одну
 * ссылку персоны на материал — он вынужден верить.
 *
 * Клик по ячейке перематывает ролик, воспроизведение подсвечивает текущую.
 * Обе связи нужны в обе стороны: по ссылке персоны находят момент, по моменту —
 * что именно модель о нём знала.
 *
 * ─── Почему загрузка в клиенте ─────────────────────────────────────────────
 * Ссылки на кадры и на ролик подписаны и живут час. Отрисованные на сервере,
 * они кешировались бы вместе со страницей и протухали молча — таймлайн выглядел
 * бы пустым без единой ошибки.
 */

interface Payload {
  video: string | null;
  timeline: TimelineView | null;
}

export function Timeline({ runId }: { runId: string }) {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentSec, setCurrentSec] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let alive = true;
    fetch(`/api/tasks/${runId}/timeline`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`сервер ответил ${r.status}`);
        return (await r.json()) as Payload;
      })
      .then((payload) => alive && setData(payload))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [runId]);

  if (error) {
    return <p className="text-sm text-slate">Таймлайн не загрузился: {error}</p>;
  }
  if (!data) {
    return <p className="text-sm text-slate">Загружаем разбор материала…</p>;
  }
  if (!data.timeline || data.timeline.cells.length === 0) {
    // Честная формулировка: пакет не сохранён — это не «материала нет», а
    // «прогон шёл до того, как разбор стал переживать контейнер».
    return (
      <p className="text-sm text-slate">
        Разбор материала не сохранён. Так выглядят прогоны, сделанные до того, как
        таймлайн стал сохраняться, — причина конкретного случая, если она была,
        записана в «Отчёт собран не полностью».
      </p>
    );
  }

  const { cells, durationSec, stats } = data.timeline;

  const seek = (sec: number) => {
    const el = videoRef.current;
    if (!el) return;
    el.currentTime = sec;
    void el.play().catch(() => {
      // Автовоспроизведение может быть запрещено политикой браузера. Перемотка
      // при этом уже случилась — этого достаточно.
    });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <div className="space-y-3">
        {data.video ? (
          /*
            Высота ограничена, ширина подстраивается — ролики бывают и 16:9, и
            9:16. При `w-full` вертикальный ролик растягивался по ширине колонки
            и уезжал на три экрана вниз: таймлайн справа оказывался напротив
            пустоты. `w-auto max-w-full` вместе с потолком высоты сохраняет
            пропорции обоих: горизонтальный упирается в ширину, вертикальный — в
            600 пикселей.
          */
          <video
            ref={videoRef}
            src={data.video}
            controls
            className="mx-auto max-h-[600px] w-auto max-w-full rounded-lg border border-hairline bg-black"
            onTimeUpdate={(e) => setCurrentSec(e.currentTarget.currentTime)}
          />
        ) : (
          <p className="rounded-lg border border-hairline bg-secondary p-4 text-sm text-slate">
            Ролик недоступен: ссылка не подписана либо файл удалён по политике
            хранения. Разбор ниже от этого не зависит.
          </p>
        )}
        {/* Полоса под плеером, а не карточки в сетке метрик: это свойства
            материала, а не результат исследования. В одном ряду с NPS они
            читались бы как показатель, который что-то говорит об аудитории. */}
        <dl className="flex flex-wrap items-baseline gap-x-5 gap-y-1 text-xs text-slate">
          {[
            ["Сцен", String(stats.scenesTotal)],
            ["Спикеров", String(stats.speakers)],
            ["Слов", String(stats.words)],
            ["Длительность", formatTime(durationSec)],
          ].map(([label, value]) => (
            <div key={label} className="flex items-baseline gap-1.5">
              <dt>{label}</dt>
              <dd className="font-medium tabular-nums text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <ol className="max-h-[600px] space-y-1 overflow-y-auto pr-1">
        {cells.map((cell, index) => (
          <Cell
            key={`${cell.start}-${index}`}
            cell={cell}
            active={currentSec >= cell.start && currentSec < cell.end}
            onSeek={() => seek(cell.start)}
          />
        ))}
      </ol>
    </div>
  );
}

function Cell({
  cell,
  active,
  onSeek,
}: {
  cell: TimelineCell;
  active: boolean;
  onSeek: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSeek}
        className={`flex w-full gap-3 rounded-md border p-2 text-left transition-colors ${
          active
            ? "border-brand-blue bg-surface-yellow"
            : "border-transparent hover:border-hairline hover:bg-secondary"
        }`}
      >
        {cell.screenshot ? (
          // Подписанная ссылка на S3 живёт час; next/image кеширует её на своей
          // стороне и отдавал бы протухшую после истечения подписи. Кадр здесь
          // 512 пикселей по ширине и рисуется в 80 — оптимизировать нечего.
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={cell.screenshot}
            alt=""
            className="h-12 w-20 shrink-0 rounded object-cover"
          />
        ) : (
          <span className="h-12 w-20 shrink-0 rounded bg-secondary" />
        )}
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2 text-xs tabular-nums text-slate">
            {formatTime(cell.start)}–{formatTime(cell.end)}
            {/* Смена сцены — только от монтажа. Разрез длинной сцены на блоки
                границей не считается: иначе экран показывал бы монтаж, которого
                в материале нет. */}
            {cell.isCut && <span className="text-[10px] uppercase">склейка</span>}
          </span>
          <span className="mt-0.5 block line-clamp-2 text-sm">
            {cell.scene ?? "до первой сцены"}
          </span>
          {/*
            Все реплики отрезка, а не первая: `truncate` на одной строке
            показывал начало первой фразы и обрывал его на полуслове, из-за чего
            по карточке нельзя было понять, о чём говорили. Ровно эту речь видит
            персона, и ровно с ней QA сверяет её ответы, — читатель отчёта
            обязан видеть то же самое. Потолок в пять строк удерживает список
            прокручиваемым: без него сцена на тридцать секунд занимала бы экран.
          */}
          {cell.lines.length > 0 && (
            <span className="mt-1 block line-clamp-5 text-xs leading-relaxed text-slate">
              {cell.lines.map((line, i) => (
                <span key={`${line.start}-${i}`}>
                  {line.speaker ? <strong className="font-medium">{line.speaker}: </strong> : null}
                  {line.text}{" "}
                </span>
              ))}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}

/** Секунды → M:SS. Часы появляются только когда они есть. */
function formatTime(sec: number): string {
  const total = Math.max(0, Math.floor(sec));
  const s = String(total % 60).padStart(2, "0");
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}
