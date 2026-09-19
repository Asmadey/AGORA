"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { humanDuration } from "@/lib/progress-state";
import { sceneColumnShare } from "@/lib/timeline-columns";
import type { TimelineCell, TimelineView } from "@/lib/server/content-pack";
import {
  isTimelineCellRendered,
  TIMELINE_INITIAL_VISIBLE,
  timelineRenderWindow,
  TIMELINE_WINDOW_OVERSCAN,
} from "@/lib/timeline-render-window";

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

/**
 * Потолок высоты плеера, в пикселях.
 *
 * Числом, а не классом: от него считается ширина колонки, и `max-h-[600px]`
 * в разметке пришлось бы держать в уме отдельно. Разойдясь, они дали бы
 * плашку не по размеру — ровно тот дефект, который чинится здесь.
 */
const PLAYER_MAX_HEIGHT = 600;

/**
 * Какую долю ширины плеер может занять, сколько бы ни просил.
 *
 * Одного потолка высоты мало. Замерено на боевом 16.09.2026: у ролика прогона
 * 0091 пропорции 2.393, и при 600 px высоты он просит 1436 px ширины — больше,
 * чем вся область содержимого (1400 px). Плеер забирал всё, а разбор сцен
 * получал свой МИНИМУМ в 22rem вместо «оставшегося пространства», которое
 * владелец и просил ему отдать.
 *
 * 0.58 даёт сценам примерно 570 px там, где прежде было 352. По прежнему
 * замеру ширины описания это переводит ячейку из «одно слово в строку, высота
 * 220 px» в «высота около 110». Дальше выигрыш уже не окупает отнятого у
 * плеера.
 *
 * Вертикальных роликов это не касается: 9:16 при 600 px просит 337 px, то есть
 * упирается в собственные пропорции задолго до доли.
 */
const PLAYER_WIDTH_SHARE = 0.58;

interface Payload {
  video: string | null;
  timeline: TimelineView | null;
}

/**
 * Откуда брать материал.
 *
 * `src` появился ради публичной ссылки: внутренняя страница читает маршрут под
 * сессией, публичная — маршрут под токеном (`/share/<токен>/timeline`).
 * Умолчание оставлено прежним, чтобы существующие вызовы не менялись, — но
 * подставляется оно ЯВНО, а не «если пусто, соберём адрес сами»: собранный
 * внутри компонента адрес однажды уехал бы в публичную страницу и упёрся бы
 * там в требование сессии.
 */
export function Timeline({
  runId,
  src,
  processingSec = null,
}: {
  runId: string;
  src?: string;
  /**
   * Сколько считался прогон. Приезжает снаружи, из Postgres через страницу:
   * второй запрос из клиента ради той же величины разошёлся бы с шапкой при
   * первом же расхождении.
   *
   * `null` значит «не показываем» — так на публичной странице, где длительность
   * нашей обработки никого не касается. Прочерк там утверждал бы «замера нет»,
   * а это неправда.
   */
  processingSec?: number | null;
}) {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentSec, setCurrentSec] = useState(0);
  /**
   * Пропорции ролика (ширина ÷ высота).
   *
   * ─── Зачем состояние, а если не знаем — 16:9 ─────────────────────────────
   * Коробка плеера обязана быть известна ДО того, как что-либо загрузится.
   * Иначе элемент берёт размер того, что сейчас внутри: сначала постера, потом
   * ролика, — и меняет его на глазах. Замерено на боевом 16.09.2026: до «play»
   * коробка 514×216 по постеру 512×214, после — по настоящему ролику.
   *
   * Виноват не «play». `preload="metadata"` стоит, но при заданном `poster`
   * Chrome метаданные не грузит: постера достаточно, чтобы что-то показать.
   * Метаданные приходят только с началом воспроизведения — отсюда и скачок
   * ровно в этот момент.
   */
  const [aspect, setAspect] = useState(16 / 9);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let alive = true;
    fetch(src ?? `/api/tasks/${runId}/timeline`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`сервер ответил ${r.status}`);
        return (await r.json()) as Payload;
      })
      .then((payload) => alive && setData(payload))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [runId, src]);

  /**
   * Первая догадка о пропорциях — по постеру.
   *
   * Постер это кадр ЭТОГО ЖЕ ролика, значит его пропорции и есть пропорции
   * ролика. Умолчание 16:9 годится как запас, но вертикальные ролики у нас
   * бывают, и на них коробка дёрнулась бы при загрузке метаданных — то есть
   * дефект вернулся бы, просто позже и реже.
   *
   * Картинка уже скачивается как постер, поэтому второй загрузки здесь нет:
   * браузер отдаёт её из кеша.
   */
  /**
   * Ширина колонок «Сцена» и «Речь» — по составу пакета.
   *
   * ─── Почему ДО ранних возвратов ──────────────────────────────────────────
   * Ниже стоят три `return` на ошибку, загрузку и пустой таймлайн. Хук после
   * них вызывался бы не на каждом рисовании, и порядок хуков поехал бы. На
   * этом уже споткнулись с `useCallback` в этом же файле — правило одно.
   *
   * ─── Почему useMemo ──────────────────────────────────────────────────────
   * Перебор долей трогает все 322 ячейки. Без памяти он повторялся бы на
   * каждой смене текущей секунды — около четырёх раз в секунду при
   * воспроизведении.
   */
  const share = useMemo(
    () => sceneColumnShare(data?.timeline?.cells ?? []),
    [data],
  );

  /**
   * Одна величина на обе сетки — шапку и каждую ячейку.
   *
   * Два места с одинаковым числом однажды разойдутся, и заголовок «РЕЧЬ»
   * встанет не над своей колонкой; заметить это можно будет только глазом.
   *
   * `useMemo` здесь не украшение, а условие работы `Cell`. Ячейка
   * мемоизирована, и объект стилей, пересобранный на каждом рисовании, — это
   * новые props: все 322 ячейки перерисовывались бы на каждой смене текущей
   * секунды. Ровно та же ловушка, что с `onSeek`.
   */
  const columns = useMemo(
    () => ({
      gridTemplateColumns: `minmax(0,${share.toFixed(2)}fr) minmax(0,${(1 - share).toFixed(2)}fr)`,
    }),
    [share],
  );

  const poster = data?.timeline?.cells.find((c) => c.screenshot)?.screenshot ?? null;
  useEffect(() => {
    if (!poster) return;
    let alive = true;
    const img = new Image();
    img.onload = () => {
      if (alive && img.naturalWidth > 0 && img.naturalHeight > 0) {
        setAspect(img.naturalWidth / img.naturalHeight);
      }
    };
    img.src = poster;
    return () => {
      alive = false;
    };
  }, [poster]);

  /**
   * Переход по таймкоду из ответа персоны: `#t=961`.
   *
   * ─── Что было ────────────────────────────────────────────────────────────
   * `TimecodeRef` рисует ссылку с подписью «Перейти к 0:49» и адресом `#t=…`,
   * а слушать этот адрес было некому. Ссылка меняла строку браузера и не
   * делала ничего — то есть обещание в подписи было ложным, и проверить
   * ссылку персоны на момент ролика было нельзя, хотя ради этого таймкоды и
   * собираются.
   *
   * ─── Почему и на загрузку, и на hashchange ───────────────────────────────
   * Первый случай — переход из другой вкладки или по ссылке из переписки:
   * страница только открывается. Второй — клик внутри уже открытой страницы:
   * адрес меняется, но React ничего не перерисовывает, и без слушателя второй
   * клик по тому же таймкоду не сработал бы вовсе.
   *
   * Плеер появляется вместе с данными, поэтому эффект зависит от `data`: на
   * пустой странице перематывать нечего.
   */
  useEffect(() => {
    if (!data) return;

    const jump = () => {
      const match = /(?:^|[#&])t=(\d+(?:\.\d+)?)/.exec(window.location.hash);
      if (!match) return;
      const el = videoRef.current;
      if (!el) return;
      el.currentTime = Number(match[1]);
      // Плеер уводится в поле зрения: таймкод в ответе персоны может быть на
      // экран ниже, и перемотка вслепую выглядит как «ничего не произошло».
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      void el.play().catch(() => {
        // Автовоспроизведение может быть запрещено политикой браузера.
        // Перемотка при этом уже случилась — этого достаточно.
      });
    };

    jump();
    window.addEventListener("hashchange", jump);
    return () => window.removeEventListener("hashchange", jump);
  }, [data]);

  /*
    Объявлен ДО ранних возвратов: хуки обязаны вызываться в одном и том же
    порядке при каждой перерисовке, а ниже стоят три `return` по состоянию
    загрузки. Первая редакция этой правки поставила `useCallback` после них —
    поймал eslint, и поймал правильно.

    `useCallback` здесь не украшение. `Cell` мемоизирован, и мемоизация
    работает лишь пока props не меняются. Функция, созданная заново на каждой
    перерисовке, отличается от прежней всегда — и memo не спасает ни одной
    ячейки из 322.
  */
  const seek = useCallback((sec: number) => {
    const el = videoRef.current;
    if (!el) return;
    el.currentTime = sec;
    void el.play().catch(() => {
      // Автовоспроизведение может быть запрещено политикой браузера. Перемотка
      // при этом уже случилась — этого достаточно.
    });
  }, []);

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

  return (
    /*
      Две области с подложкой и зазором между ними, а не один сплошной блок:
      слева смотрят, справа выбирают, и по общему фону это читалось как одна
      панель, где список — продолжение плеера. Скругление 5px намеренно мельче
      карточек отчёта (8px): это рабочая поверхность, а не карточка с выводом.

      ─── Почему ширину задаёт сетка, а не ролик ──────────────────────────────
      Здесь стояло `lg:grid-cols-[auto_minmax(0,1fr)]`, и 16.09.2026 на прогоне
      0091 это дало 1306 пикселей плееру и 84 — панели сцен: заголовки «СЦЕНА» и
      «РЕЧЬ» налезали друг на друга.

      `auto` — это `minmax(min-content, max-content)`. Пока браузер не знает
      размеров ролика, max-content мал и колонки выглядят правильно. Как только
      метаданные доехали, max-content становится исходной шириной ролика (здесь
      1280), и трек разрастается до неё. Выглядит это как «сломалось от нажатия
      play», но play лишь торопит загрузку метаданных — то же самое случится
      само, если подождать.

      Панель сцен не была защищена ничем: у `minmax(0,1fr)` минимум нулевой, то
      есть она обязана отдать всё, что потребует сосед.

      Теперь наоборот: плеер берёт остаток (`minmax(0,1fr)` — минимум нулевой
      именно затем, чтобы содержимое не могло его раздуть), а у панели сцен есть
      пол в 22rem и потолок в 40rem.

      Потолок нужен не меньше пола: список сцен — колонка для чтения, и на
      широком мониторе растягивать её незачем. Обе границы подобраны замером на
      боевом прогоне 0091, а не на глаз: ширина описания сцены — это ширина
      панели за вычетом превью и колонки речи, и она растёт линейно. При панели
      в 320px описанию достаётся 24 пикселя (одно слово в строку, высота ячейки
      220px), при 448 — 80, при 640 — 164 и высота падает до 100. Дальше выигрыш
      уже не окупает отнятого у плеера.
    */
    <div
      className="grid gap-4 lg:grid-cols-[minmax(0,var(--player-col))_minmax(22rem,1fr)]"
      /*
        Ширина левой колонки — ширина ПЛЕЕРА плюс отступы плашки.

        Прежде здесь стояло `minmax(0,1fr)_minmax(22rem,40rem)`: плеер брал
        остаток, а панель сцен — от 22rem до 40rem. Плашка при этом получалась
        744 px вокруг ролика в 514 — «сильно выходит за рамки плеера», как это и
        назвал владелец.

        Теперь наоборот: колонка считается от плеера, остаток достаётся разбору
        сцен — там описания и реплики, и ширина им нужна.

        `1.5rem` — это `p-3` плашки с обеих сторон. Величина повторена здесь
        намеренно и проверяется тестом: вычислить её из класса нельзя, а
        разойтись они могут молча.
      */
      style={
        {
          "--player-col": `min(calc(${Math.round(PLAYER_MAX_HEIGHT * aspect)}px + 1.5rem), ${
            PLAYER_WIDTH_SHARE * 100
          }%)`,
        } as React.CSSProperties
      }
    >
      {/*
        `w-full`, а не `w-fit`: обёртка, считаемая по содержимому, возвращает ту
        же круговую зависимость — `max-w-full` у ролика считается в процентах от
        ширины, которая сама считается от ролика. Ширина колонки определённая,
        и от неё процент считается однозначно.
      */}
      {/*
        `self-start`: плашка по высоте своего содержимого, а не соседа.

        Элементы сетки по умолчанию растягиваются на всю строку, а высоту
        строки задаёт разбор сцен — у него потолок 600 px. Пока ролик был
        высотой в те же 600, это совпадало. После перехода на заданные
        пропорции широкий ролик стал 329 px высотой, и под полосой свойств
        осталось больше двухсот пикселей пустого серого.
      */}
      <div className="w-full self-start space-y-3 rounded-[5px] bg-secondary/50 p-3">
        {data.video ? (
          /*
            Высота ограничена, ширина подстраивается — ролики бывают и 16:9, и
            9:16. При `w-full` вертикальный ролик растягивался по ширине колонки
            и уезжал на три экрана вниз: таймлайн справа оказывался напротив
            пустоты. `w-auto max-w-full` вместе с потолком высоты сохраняет
            пропорции обоих: горизонтальный упирается в ширину, вертикальный — в
            600 пикселей.
          */
          <div
            /*
              Коробка с ЗАДАННЫМИ пропорциями. Ролик внутри вписывается в неё
              (`object-contain`), а не задаёт её собой — поэтому подмена постера
              настоящим кадром ничего не двигает.

              Потолок высоты остаётся: он стоял ради вертикальных роликов, и на
              9:16 без него плеер уехал бы на три экрана вниз, оставив таймлайн
              справа напротив пустоты.
            */
            className="mx-auto w-full overflow-hidden rounded-lg border border-hairline bg-black"
            style={{
              aspectRatio: String(aspect),
              maxHeight: PLAYER_MAX_HEIGHT,
              maxWidth: Math.round(PLAYER_MAX_HEIGHT * aspect),
            }}
          >
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
            className="h-full w-full object-contain"
            /*
              Целая секунда, а не дробная. `timeupdate` приходит примерно
              четыре раза в секунду, и при дробном значении каждое из них
              меняло состояние, то есть перерисовывало список. Подсветка
              ячейки от округления не страдает: ячейки длятся 5–30 секунд.
            */
            onTimeUpdate={(e) => setCurrentSec(Math.floor(e.currentTarget.currentTime))}
            /*
              Метаданные уточняют догадку по постеру. Приходят они поздно — при
              заданном `poster` Chrome откладывает их до начала воспроизведения,
              — но к этому моменту коробка уже задана, и уточнение либо не меняет
              ничего, либо поправляет пропорции на доли процента.
            */
            onLoadedMetadata={(e) => {
              const { videoWidth, videoHeight } = e.currentTarget;
              if (videoWidth > 0 && videoHeight > 0) setAspect(videoWidth / videoHeight);
            }}
          />
          </div>
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
            // Замер прогона стоит ПРАВЕЕ длительности ролика и рядом с ней —
            // это два времени, и рядом видно, что одно про материал, а второе
            // про нашу обработку. В сетке показателей, среди NPS и оценок,
            // второе читалось как величина, что-то говорящая об аудитории.
            ...(processingSec !== null
              ? [["Время обработки", humanDuration(processingSec)] as [string, string]]
              : []),
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
      <TimelineList cells={cells} currentSec={currentSec} onSeek={seek} columns={columns} />
    </div>
  );
}

/**
 * Окно списка. Пустые строки остаются лёгкими якорями, чтобы IntersectionObserver
 * знал, где находится прокрутка; тяжёлая Cell монтируется только в окне.
 */
function TimelineList({
  cells,
  currentSec,
  onSeek,
  columns,
}: {
  cells: TimelineCell[];
  currentSec: number;
  onSeek: (sec: number) => void;
  columns: React.CSSProperties;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef(new Map<number, HTMLLIElement>());
  const intersectionObserver = useRef<IntersectionObserver | null>(null);
  const resizeObserver = useRef<ResizeObserver | null>(null);
  const intersecting = useRef(new Set<number>());
  const heights = useRef(new Map<number, number>());
  const [rowHeights, setRowHeights] = useState<Record<number, number>>({});
  const [renderWindow, setRenderWindow] = useState(() =>
    timelineRenderWindow(cells.length, 0, Math.min(cells.length, TIMELINE_INITIAL_VISIBLE)),
  );
  const [printing, setPrinting] = useState(false);

  const sceneNumbers = useMemo(() => {
    let sceneNo = 0;
    return cells.map((cell) => (cell.scene === null ? null : ++sceneNo));
  }, [cells]);

  const activeIndex = cells.findIndex(
    (cell) => currentSec >= cell.start && currentSec < cell.end,
  );

  useEffect(() => {
    setRenderWindow(
      timelineRenderWindow(cells.length, 0, Math.min(cells.length, TIMELINE_INITIAL_VISIBLE)),
    );
    intersecting.current.clear();
  }, [cells.length]);

  useEffect(() => {
    const updateWindow = () => {
      const indexes = [...intersecting.current].sort((a, b) => a - b);
      if (indexes.length === 0) return;
      const next = timelineRenderWindow(
        cells.length,
        indexes[0],
        indexes[indexes.length - 1] + 1,
        TIMELINE_WINDOW_OVERSCAN,
      );
      setRenderWindow((previous) =>
        previous.start === next.start && previous.end === next.end ? previous : next,
      );
    };

    const root = scrollRef.current;
    if (!root || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const index = Number((entry.target as HTMLElement).dataset.timelineIndex);
          if (!Number.isInteger(index)) continue;
          if (entry.isIntersecting) intersecting.current.add(index);
          else intersecting.current.delete(index);
        }
        updateWindow();
      },
      { root, rootMargin: "0px", threshold: 0 },
    );
    intersectionObserver.current = observer;
    for (const row of rowRefs.current.values()) observer.observe(row);

    return () => {
      observer.disconnect();
      intersectionObserver.current = null;
    };
  }, [cells.length]);

  useEffect(() => {
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      let changed = false;
      const updates: Array<[number, number]> = [];
      for (const entry of entries) {
        const index = Number((entry.target as HTMLElement).dataset.timelineIndex);
        const height = Math.ceil(entry.contentRect.height);
        if (!Number.isInteger(index) || height <= 0 || heights.current.get(index) === height) {
          continue;
        }
        heights.current.set(index, height);
        updates.push([index, height]);
        changed = true;
      }
      if (changed) {
        setRowHeights((previous) => {
          const next = { ...previous };
          for (const [index, height] of updates) next[index] = height;
          return next;
        });
      }
    });
    resizeObserver.current = observer;
    for (const row of rowRefs.current.values()) observer.observe(row);

    return () => {
      observer.disconnect();
      resizeObserver.current = null;
    };
  }, [cells.length]);

  useEffect(() => {
    const beforePrint = () => setPrinting(true);
    const afterPrint = () => setPrinting(false);
    window.addEventListener("beforeprint", beforePrint);
    window.addEventListener("afterprint", afterPrint);

    const media = window.matchMedia("print");
    const onMediaChange = (event: MediaQueryListEvent) => setPrinting(event.matches);
    media.addEventListener?.("change", onMediaChange);

    return () => {
      window.removeEventListener("beforeprint", beforePrint);
      window.removeEventListener("afterprint", afterPrint);
      media.removeEventListener?.("change", onMediaChange);
    };
  }, []);

  const registerRow = useCallback((index: number, node: HTMLLIElement | null) => {
    const previous = rowRefs.current.get(index);
    if (previous && previous !== node) {
      intersectionObserver.current?.unobserve(previous);
      resizeObserver.current?.unobserve(previous);
    }
    if (!node) {
      rowRefs.current.delete(index);
      intersecting.current.delete(index);
      return;
    }
    node.dataset.timelineIndex = String(index);
    rowRefs.current.set(index, node);
    intersectionObserver.current?.observe(node);
    resizeObserver.current?.observe(node);
  }, []);

  return (
    <div ref={scrollRef} className="max-h-[600px] overflow-y-auto rounded-[5px] bg-secondary/50 p-3">
        <div
          className="mb-2 grid gap-3 px-2 text-[11px] uppercase tracking-wide text-slate"
          style={columns}
        >
          <span>Сцена</span>
          <span>Речь</span>
        </div>
        <ol className="space-y-1">
          {cells.map((cell, index) => {
            const rendered = printing || isTimelineCellRendered(index, renderWindow, activeIndex);
            const measuredHeight = rowHeights[index];

            return (
              <li
                key={`${cell.start}-${index}`}
                ref={(node) => registerRow(index, node)}
                style={{ minHeight: measuredHeight ?? 112 }}
                className={rendered ? undefined : "[content-visibility:auto]"}
                aria-hidden={rendered ? undefined : true}
              >
                {rendered ? (
                  <Cell
                    cell={cell}
                    sceneNumber={sceneNumbers[index]}
                    active={currentSec >= cell.start && currentSec < cell.end}
                    onSeek={onSeek}
                    columns={columns}
                    printMode={printing}
                  />
                ) : null}
              </li>
            );
          })}
        </ol>
        <div className="sr-only" data-timeline-search-index>
          {cells.map((cell, index) => (
            <p key={`search-${cell.start}-${index}`}>
              {cell.lines.map((line) => `${line.speaker ? `${line.speaker}: ` : ""}${line.text}`).join(" ")}
            </p>
          ))}
        </div>
      </div>
  );
}

/**
 * Ячейка сцены.
 *
 * ─── Почему memo ──────────────────────────────────────────────────────────
 * Ход воспроизведения меняет текущую секунду, и без мемоизации каждая такая
 * смена перерисовывала все 322 ячейки — с превью, репликами и всем прочим.
 * На сорокавосьмиминутном ролике это 322 ячейки против двух, у которых
 * подсветка действительно изменилась.
 *
 * Мемоизация держится на двух условиях сразу, и оба легко потерять:
 * `onSeek` приходит стабильной ссылкой (`useCallback` у родителя), а
 * `currentSec` округлён до целых секунд. Нарушение любого из них вернёт
 * перерисовку всего списка молча — экран будет выглядеть правильно, просто
 * станет тяжёлым. Оба условия держит `lib/timeline-render.test.ts`.
 */
const Cell = memo(function Cell({
  cell,
  sceneNumber,
  active,
  onSeek,
  columns,
  printMode,
}: {
  cell: TimelineCell;
  /** Порядковый номер сцены. null — реплики до первой сцены, это не сцена. */
  sceneNumber: number | null;
  active: boolean;
  onSeek: (sec: number) => void;
  printMode: boolean;
  /**
   * Доли колонок «Сцена» и «Речь». Приходит СТАБИЛЬНОЙ ссылкой (`useMemo` у
   * родителя): пересобранный объект стилей — это новые props, и мемоизация
   * ячейки перестаёт значить что-либо.
   */
  columns: React.CSSProperties;
}) {
  return (
    /*
      `content-visibility: auto` разрешает браузеру не размечать и не красить
      ячейку, пока она за пределами прокрутки. Из 322 ячеек видно три.

      `contain-intrinsic-size` обязателен рядом: без предполагаемой высоты
      невидимая ячейка считается нулевой, полоса прокрутки скачет при каждом
      измерении. Ключевое слово `auto` велит браузеру запомнить настоящую
      высоту, когда ячейка один раз показалась, — дальше догадка не нужна.
      112px — медиана замеренных высот ячейки на прогоне 0091.
    */
    <div className={printMode ? undefined : "[content-visibility:auto] [contain-intrinsic-size:auto_112px]"}>
      <button
        type="button"
        onClick={() => onSeek(cell.start)}
        style={columns}
        className={`grid w-full gap-3 rounded-md border p-2 text-left transition-colors ${
          active
            ? "border-brand-blue bg-surface-yellow"
            : "border-transparent hover:border-hairline hover:bg-secondary"
        }`}
      >
        {/* Левая часть: обложка, таймкод, описание кадра. */}
        <span className="flex min-w-0 gap-3">
          {/*
            Кадр и номер — одна колонка: номер подписывает именно картинку, а не
            стоит третьим элементом в ряду. `shrink-0` переехал сюда с самого
            кадра — без него восемьдесят пикселей превью схлопываются в узкой
            колонке, и подпись съезжает вместе с ними.
          */}
          <span className="flex shrink-0 flex-col items-center gap-1">
          {cell.screenshot ? (
            // Подписанная ссылка на S3 живёт час; next/image кеширует её на своей
            // стороне и отдавал бы протухшую после истечения подписи. Кадр здесь
            // 512 пикселей по ширине и рисуется в 80 — оптимизировать нечего.
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={cell.screenshot}
              alt=""
              /*
                `lazy` и явные размеры — одно решение, а не два. Замер на
                прогоне 0091: 322 кадра выкачивались, чтобы показать три, и
                эти 322 параллельных запроса к S3 душили сам ролик — после
                нажатия «play» `readyState` десять секунд держался в нуле.

                Размеры обязательны именно здесь: без них браузер не знает,
                сколько места займёт картинка, не может отложить загрузку без
                скачка разметки — и грузит сразу. Числа те же, что в классах
                (w-20 h-12 = 80×48), и расходиться им нельзя.
              */
              loading="lazy"
              decoding="async"
              width={80}
              height={48}
              className="h-12 w-20 rounded object-cover"
            />
          ) : (
            <span className="h-12 w-20 rounded bg-secondary" />
          )}
            {/*
              Номер, а не индекс: на сцену ссылаются номером и в отчёте, и в
              ответах персон, и в разговоре — «сцена 47» короче и устойчивее,
              чем «12:03–12:19». У реплик до первой сцены номера нет, и место
              под него не занимается: пустая подпись читалась бы как потерянный
              номер.
            */}
            {sceneNumber !== null && (
              <span className="text-[10px] tabular-nums leading-none text-slate">
                {sceneNumber}
              </span>
            )}
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2 text-xs tabular-nums text-slate">
              {formatTime(cell.start)}–{formatTime(cell.end)}
              {/* Смена сцены — только от монтажа. Разрез длинной сцены на блоки
                  границей не считается: иначе экран показывал бы монтаж, которого
                  в материале нет. */}
              {cell.isCut && <span className="text-[10px] uppercase">склейка</span>}
            </span>
            {/*
              Описание показывается целиком. Здесь стоял `line-clamp-3`, и он
              обрезал ровно так же молча, как `max-h-24` обрезал речь: замер на
              боевом 18.09.2026, прогон 0092, — «Сцена показывает группу
              солдат…» занимала 120 px, а показывалось 100.
            */}
            <span className="mt-0.5 block text-sm">
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
            /*
              Высота — по объёму реплики, без потолка.

              Здесь стояло `max-h-24 overflow-hidden`. Замер в браузере на
              боевом 18.09.2026, `/runs/0092`, окно 1512×792: колонка речи
              182 px, `scrollHeight` 160 против `clientHeight` 96 — то есть
              64 px, около четырёх строк, отрезаны без единого признака того,
              что они были. Обрезается при этом ровно та ячейка, где речи
              много, — ровно та, ради которой колонку и читают.

              Потолок вдобавок спорил с `lib/timeline-columns.ts`: пропорция
              колонок там подбирается перебором так, чтобы СУММАРНАЯ ВЫСОТА
              ленты была наименьшей, и высота каждой строки считается по
              ПОЛНОМУ тексту обеих колонок. Подобрать ширину под текст, а потом
              отрезать текст по высоте — значит решать задачу и выбрасывать её
              решение.

              Цена замерена там же: снятие обеих обрезок удлинило ленту 0092 на
              11 % (376 → 418 px).
            */
            <span className="block space-y-1 text-xs leading-relaxed">
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
    </div>
  );
});

/** Секунды → M:SS. Часы появляются только когда они есть. */
function formatTime(sec: number): string {
  const total = Math.max(0, Math.floor(sec));
  const s = String(total % 60).padStart(2, "0");
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}
