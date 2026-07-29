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
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="tabular-nums text-sm font-medium">
          {value.toFixed(1)}
          {confidence && (
            <span className="ml-1.5 text-xs font-normal text-muted-foreground">
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
          <span className="w-44 shrink-0 text-sm text-muted-foreground">
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
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass = {
    default: "text-foreground",
    good: "text-emerald-400",
    warn: "text-amber-400",
    bad: "text-rose-400",
  }[tone];

  return (
    <div className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("mt-1.5 text-2xl font-semibold tabular-nums", toneClass)}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
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
        tone === "outline" && "border border-border text-muted-foreground",
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
    <div className="border-b border-border/60 py-2 last:border-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("mt-0.5 text-sm", !text && "italic text-muted-foreground/60")}>
        {text || "не задано"}
      </dd>
    </div>
  );
}

/** Ссылка на таймкод. Каждое суждение персоны обязано на что-то опираться. */
export function TimecodeRef({ timecode, note }: { timecode: string; note: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-border px-2 py-0.5 text-xs">
      <span className="font-mono tabular-nums text-sky-300">{timecode}</span>
      <span className="text-muted-foreground">{note}</span>
    </span>
  );
}

/** Материал — гипотеза, а не измерение. Это должно быть видно в интерфейсе. */
export function HypothesisNotice({ replication }: { replication: number }) {
  return (
    <p className="rounded-md border border-amber-500/25 bg-amber-500/5 px-4 py-3 text-xs leading-relaxed text-amber-200/80">
      Это прогноз на синтетической аудитории, а не результат опроса живых людей.
      Оценки заземлены на корпус из 165 реальных респондентов и откалиброваны по нему,
      но требуют экспертной проверки перед решением.
      {replication > 1
        ? ` Каждая персона прошла анкету ${replication} раза — на шкалах показан разброс между повторами.`
        : " Перекрытие равно 1: разброс не измерялся, доверительные границы недоступны."}
    </p>
  );
}
