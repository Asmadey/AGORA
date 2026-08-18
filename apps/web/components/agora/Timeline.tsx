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
    /*
      Две области с подложкой и зазором между ними, а не один сплошной блок:
      слева смотрят, справа выбирают, и по общему фону это читалось как одна
      панель, где список — продолжение плеера. Скругление 5px намеренно мельче
      карточек отчёта (8px): это рабочая поверхность, а не карточка с выводом.
    */
    <div className="grid gap-4 lg:grid-cols-[auto_minmax(0,1fr)]">
      <div className="mx-auto w-fit space-y-3 rounded-[5px] bg-secondary/50 p-3 lg:mx-0">
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
            /*
              Постер — первый кадр таймлайна, а не отдельно снятая картинка.
              Отдельная означала бы ещё один проход ffmpeg по ролику ради того,
              что уже лежит в S3: кадры сцен выгружаются разбором и подписаны
              тем же способом. Без постера браузер до нажатия «play» показывает
              чёрный прямоугольник, и на вертикальном ролике это полэкрана
              пустоты.
            */
            poster={cells.find((c) => c.screenshot)?.screenshot ?? undefined}
            preload="metadata"
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

      {/*
        Одна прокрутка на обе части, а не две колонки со своими полосами.
        Раздельная прокрутка разъезжается на первом же движении колеса: слева
        сцена 1:20, справа речь из 0:30, и подсветка «обеих частей» показывает
        два места, которые ничего общего не имеют. Строка держит их рядом по
        построению.
      */}
      <div className="max-h-[600px] overflow-y-auto rounded-[5px] bg-secondary/50 p-3">
        <div className="mb-2 grid grid-cols-[minmax(0,7fr)_minmax(0,9fr)] gap-3 px-2 text-[11px] uppercase tracking-wide text-slate">
          <span>Сцена</span>
          <span>Речь</span>
        </div>
        <ol className="space-y-1">
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
        className={`grid w-full grid-cols-[minmax(0,7fr)_minmax(0,9fr)] gap-3 rounded-md border p-2 text-left transition-colors ${
          active
            ? "border-brand-blue bg-surface-yellow"
            : "border-transparent hover:border-hairline hover:bg-secondary"
        }`}
      >
        {/* Левая часть: обложка, таймкод, описание кадра. */}
        <span className="flex min-w-0 gap-3">
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
            <span className="mt-0.5 block line-clamp-3 text-sm">
              {cell.scene ?? "до первой сцены"}
            </span>
          </span>
        </span>

        {/*
          Правая часть: речь по репликам. Каждая — своей строкой с отступом, а не
          сплошным абзацем: слитный текст двух спикеров читается как монолог, и
          по нему нельзя понять, кто кому отвечает. Ровно эту речь видит персона,
          и ровно с ней QA сверяет её ответы.
        */}
        <span className="min-w-0 border-l border-hairline pl-3">
          {cell.lines.length > 0 ? (
            <span className="block max-h-24 space-y-1 overflow-hidden text-xs leading-relaxed">
              {cell.lines.map((line, i) => (
                <span key={`${line.start}-${i}`} className="block pl-2 -indent-2">
                  {line.speaker ? (
                    <strong className="font-medium text-foreground">{line.speaker}: </strong>
                  ) : null}
                  <span className="text-slate">{line.text}</span>
                </span>
              ))}
            </span>
          ) : (
            <span className="block text-xs text-slate">— тишина</span>
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
