import { cn } from "@/lib/utils";
import type { BigFive, Confidence } from "@/lib/agora-types";

/**
 * Мелкие визуальные примитивы отчёта и карточки персоны.
 *
 * Сделаны на голом SVG и CSS, без графической библиотеки: диаграммы здесь простые,
 * а лишняя зависимость в бандле дороже, чем тридцать строк разметки.
 */

/** Балл 1–10. Цвет несёт смысл: ниже 6 — проблема, выше 8 — сила материала. */
export function ScoreBar({
  label,
  value,
  confidence,
  max = 10,
}: {
  label: string;
  value: number;
  confidence?: Confidence;
  max?: number;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const tone =
    value >= 8 ? "bg-emerald-400" : value >= 6.5 ? "bg-sky-400" : "bg-amber-400";

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="text-sm text-slate">{label}</span>
        <span className="tabular-nums text-sm font-medium">
          {value.toFixed(1)}
          {confidence && (
            <span className="ml-1.5 text-xs font-normal text-slate">
              ±{confidence.stdev.toFixed(2)}
            </span>
          )}
        </span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-secondary">
        <div className={cn("h-full rounded-full transition-all", tone)} style={{ width: `${pct}%` }} />
        {/* Разброс по повторам показываем прямо на шкале: одно число без разброса
            создаёт ложное ощущение точности, особенно при replication > 1. */}
        {confidence && (
          <div
            className="absolute inset-y-0 bg-foreground/20"
            style={{
              left: `${(confidence.min / max) * 100}%`,
              width: `${((confidence.max - confidence.min) / max) * 100}%`,
            }}
          />
        )}
      </div>
    </div>
  );
}

const BIG_FIVE_LABELS: Record<keyof BigFive, string> = {
  openness: "Открытость опыту",
  conscientiousness: "Добросовестность",
  extraversion: "Экстраверсия",
  agreeableness: "Доброжелательность",
  neuroticism: "Нейротизм",
};

/** Big Five по шкале 1–5 (Decision Log #7) — точками, а не полосами: шкала короткая. */
export function BigFiveChart({ value }: { value: BigFive }) {
  return (
    <div className="space-y-3">
      {(Object.keys(BIG_FIVE_LABELS) as (keyof BigFive)[]).map((key) => (
        <div key={key} className="flex items-center gap-3">
          <span className="w-44 shrink-0 text-sm text-slate">
            {BIG_FIVE_LABELS[key]}
          </span>
          <div className="flex gap-1.5">
            {[1, 2, 3, 4, 5].map((n) => (
              <span
                key={n}
                className={cn(
                  "h-2.5 w-2.5 rounded-full",
                  n <= value[key] ? "bg-foreground" : "bg-secondary",
                )}
              />
            ))}
          </div>
          <span className="tabular-nums text-sm font-medium">{value[key]}</span>
        </div>
      ))}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  rationale,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  /**
   * Почему число такое — фразой из вербатимов персон.
   *
   * Отдельно от `hint`: подпись объясняет ШКАЛУ («из 10», «−100…+100»), а
   * обоснование — результат. Слив их в одно поле, мы бы получили карточку, где
   * не разобрать, что здесь свойство метрики, а что вывод по этому материалу.
   */
  rationale?: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass = {
    default: "text-foreground",
    good: "text-success",
    warn: "text-amber-400",
    bad: "text-danger",
  }[tone];

  return (
    <div className="rounded-lg border border-hairline bg-card p-4">
      <p className="text-xs uppercase tracking-wide text-slate">{label}</p>
      <p className={cn("mt-1.5 text-2xl font-semibold tabular-nums", toneClass)}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate">{hint}</p>}
      {rationale && (
        <p className="mt-2 border-t border-hairline pt-2 text-xs leading-relaxed text-foreground/80">
          {rationale}
        </p>
      )}
    </div>
  );
}

export function Chip({
  children,
  tone = "muted",
}: {
  children: React.ReactNode;
  tone?: "muted" | "outline" | "solid";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs",
        tone === "muted" && "bg-secondary text-secondary-foreground",
        tone === "outline" && "border border-hairline text-slate",
        tone === "solid" && "bg-foreground text-background",
      )}
    >
      {children}
    </span>
  );
}

/** Поле карточки персоны. Пустые значения не скрываем — видно, что данных нет. */
export function Field({ label, value }: { label: string; value?: string | string[] }) {
  const text = Array.isArray(value) ? value.join(", ") : value;
  return (
    <div className="border-b border-hairline/60 py-2 last:border-0">
      <dt className="text-xs text-slate">{label}</dt>
      <dd className={cn("mt-0.5 text-sm", !text && "italic text-slate/60")}>
        {text || "не задано"}
      </dd>
    </div>
  );
}

/**
 * Позиция таймкода в секундах. `null` — строка не таймкод.
 *
 * Разбираются M:SS, MM:SS и H:MM:SS. Секунды ограничены 0–59: без этого «10:75»
 * и любая пара чисел через двоеточие читались бы как время, и ссылка вела бы в
 * никуда — причём выглядела бы рабочей.
 */
export function timecodeSeconds(timecode: string): number | null {
  const m = /^(\d{1,2}):([0-5]\d)(?::([0-5]\d))?$/.exec(timecode.trim());
  if (!m) return null;
  const [, a, b, c] = m;
  return c ? Number(a) * 3600 + Number(b) * 60 + Number(c) : Number(a) * 60 + Number(b);
}

/**
 * Ссылка на таймкод. Каждое суждение персоны обязано на что-то опираться.
 *
 * Приёмка задачи #21 требует, чтобы обоснование было кликабельно И вело на
 * таймкод. Второе — не то же самое, что первое: кнопка без адреса кликается и
 * не ведёт никуда, а отличить её от рабочей на скриншоте нельзя.
 *
 * Адресом служит медиафрагмент `#t=<секунды>` (W3C Media Fragments) — тот же
 * якорь понимает и HTML-плеер, и прямая ссылка на файл. Поэтому ссылка остаётся
 * осмысленной и до того, как на экране появится сам плеер: она указывает на
 * позицию, а не на элемент интерфейса.
 *
 * Неразобранный таймкод не превращается в ссылку: якорь `#t=NaN` кликался бы и
 * не вёл никуда — ровно тот случай, который проверка и должна исключать.
 */
export function TimecodeRef({
  timecode,
  note,
  href = "",
}: {
  timecode: string;
  note: string;
  /** Куда ведёт таймкод. Пусто — текущая страница. */
  href?: string;
}) {
  const seconds = timecodeSeconds(timecode);
  const body = (
    <>
      <span className="font-mono tabular-nums text-brand-blue">{timecode}</span>
      <span className="text-slate">{note}</span>
    </>
  );
  const shell = "inline-flex items-center gap-1.5 rounded border border-hairline px-2 py-0.5 text-xs";

  if (seconds === null) {
    return <span className={shell}>{body}</span>;
  }
  return (
    <a
      href={`${href}#t=${seconds}`}
      title={`Перейти к ${timecode}`}
      className={`${shell} transition-colors hover:border-sky-400/60 hover:bg-sky-400/5`}
    >
      {body}
    </a>
  );
}

// HypothesisNotice убран по просьбе владельца: жёлтая плашка на весь экран
// повторяла дисклеймер, который и так стоит внизу отчёта, и занимала первый
// экран — то место, ради которого страницу открывают.
//
// Один факт из неё сохранён по месту: при перекрытии 1 разброс не измерялся,
// и об этом сказано рядом со шкалами, где это имеет значение.
