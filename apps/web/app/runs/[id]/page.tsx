import Link from "next/link";
import { notFound } from "next/navigation";
import { MessageCircle, RotateCcw } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import {
  Chip,
  HypothesisNotice,
  ScoreBar,
  StatCard,
} from "@/components/agora/Primitives";
import { PersonaAccordion } from "@/components/agora/PersonaAccordion";
import { ShareDialog } from "@/components/agora/ShareDialog";
import { MOCK_PERSONAS, MOCK_RUNS } from "@/lib/mock-data";
import { CRITERIA, CRITERIA_LABELS } from "@/lib/agora-types";

/**
 * Экран отчёта (PRD §5.E, §6): агрегат и графики сверху, аккордеон по персонам снизу.
 *
 * Порядок блоков отвечает порядку вопросов пользователя: «сколько?» → «почему?» →
 * «кто именно так сказал?». Групповой синтез стоит выше персон, потому что решение
 * принимают по темам, а не по отдельным репликам.
 */
export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = MOCK_RUNS.find((r) => r.id === id);
  // Явный return вместо опоры на never-возврат notFound() — см. комментарий
  // в карточке персоны.
  if (!run) {
    notFound();
    return null;
  }

  if (run.status !== "REPORT_READY" || !run.aggregate) {
    return (
      <div className="p-8">
        <p className="text-muted-foreground">
          Отчёт ещё не готов.{" "}
          <Link href={`/runs/${run.id}/progress`} className="underline underline-offset-4">
            Смотреть прогресс
          </Link>
        </p>
      </div>
    );
  }

  const { aggregate: agg, synthesis, answers = [] } = run;

  return (
    <>
      <PageHeader
        title={run.projectName}
        subtitle={`${run.contentTitle} · ${run.audienceSize} персон · перекрытие ${run.replicationCount}`}
        actions={
          <>
            <Link
              href={`/runs/${run.id}/chat`}
              className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
            >
              <MessageCircle className="h-4 w-4" />
              Обсудить результаты
            </Link>
            <Link
              href={`/studies/new?rerun=${run.id}`}
              className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
            >
              <RotateCcw className="h-4 w-4" />
              Перезапустить
            </Link>
            <ShareDialog />
          </>
        }
      />

      <div className="space-y-8 p-8">
        <HypothesisNotice replication={run.replicationCount} />

        {/* Сводные метрики */}
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Общее впечатление"
            value={agg.scores.overall_impression.toFixed(1)}
            hint="из 10"
          />
          <StatCard
            label="NPS"
            value={String(agg.nps)}
            hint="доля промоутеров минус критиков"
            tone={agg.nps < 0 ? "bad" : agg.nps > 30 ? "good" : "warn"}
          />
          <StatCard
            label="Досмотр"
            value={`${agg.retentionRate.toFixed(1)}%`}
            hint="средняя доля просмотренного"
            tone={agg.retentionRate < 70 ? "warn" : "good"}
          />
          <StatCard
            label="Эмоциональный индекс"
            value={agg.emotionalIndex.toFixed(1)}
            hint="из 10"
          />
        </section>

        {/* Нарратив: главный текст отчёта */}
        {run.narrative && (
          <section className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-6">
            <h2 className="mb-3 text-sm font-semibold">Что показало исследование</h2>
            <div className="space-y-3 text-sm leading-relaxed">
              {run.narrative.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
          </section>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Критерии */}
          <section className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-6">
            <h2 className="text-sm font-semibold">Оценки по критериям</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Затемнённая зона на шкале — разброс между повторами
            </p>
            <div className="mt-5 space-y-4">
              {CRITERIA.map((c) => (
                <ScoreBar
                  key={c}
                  label={CRITERIA_LABELS[c]}
                  value={agg.scores[c]}
                  confidence={agg.confidence?.[c]}
                />
              ))}
            </div>
          </section>

          {/* Эмоции */}
          <section className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-6">
            <h2 className="text-sm font-semibold">Преобладающие эмоции</h2>
            <div className="mt-5 space-y-3">
              {agg.topEmotions.map((e) => (
                <div key={e.name} className="flex items-center gap-3">
                  <span className="w-36 shrink-0 text-sm text-muted-foreground">{e.name}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                    <div className="h-full rounded-full bg-foreground/70" style={{ width: `${e.pct}%` }} />
                  </div>
                  <span className="w-10 shrink-0 text-right text-sm tabular-nums">{e.pct}%</span>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* Сегменты */}
        <section>
          <h2 className="mb-3 text-sm font-semibold">Срез по сегментам</h2>
          <div className="grid gap-3 md:grid-cols-3">
            {agg.segments.map((s) => (
              <div key={s.segment} className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5">
                <div className="flex items-baseline justify-between">
                  <Chip tone="solid">{s.segment}</Chip>
                  <span className="text-2xl font-semibold tabular-nums">
                    {s.scores.overall_impression.toFixed(1)}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{s.note}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Групповой синтез */}
        {synthesis && (
          <section>
            <h2 className="mb-1 text-sm font-semibold">Групповой синтез</h2>
            <p className="mb-4 text-xs text-muted-foreground">
              Темы, по которым персоны сошлись или разошлись
            </p>
            <div className="space-y-3">
              {synthesis.themes.map((t) => (
                <div key={t.title} className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 className="font-medium">{t.title}</h3>
                    <Chip
                      tone={t.agreement === "раскол" ? "solid" : "muted"}
                    >
                      {t.agreement}
                    </Chip>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{t.summary}</p>
                  <div className="mt-4 space-y-2">
                    {t.quotes.map((q, i) => (
                      <blockquote key={i} className="border-l-2 border-border pl-3 text-sm">
                        «{q.text}»
                        <span className="ml-2 text-xs text-muted-foreground">
                          — {q.persona}
                          {q.timecode && (
                            <span className="ml-1.5 font-mono text-sky-300">{q.timecode}</span>
                          )}
                        </span>
                      </blockquote>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-5">
                <h3 className="text-sm font-semibold text-emerald-300">Сильные стороны</h3>
                <ul className="mt-3 space-y-1.5 text-sm">
                  {synthesis.strengths.map((s) => (
                    <li key={s} className="text-muted-foreground">— {s}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-5">
                <h3 className="text-sm font-semibold text-amber-300">Что проседает</h3>
                <ul className="mt-3 space-y-1.5 text-sm">
                  {synthesis.weaknesses.map((s) => (
                    <li key={s} className="text-muted-foreground">— {s}</li>
                  ))}
                </ul>
              </div>
            </div>
          </section>
        )}

        {/* Персоны */}
        <section>
          <h2 className="mb-1 text-sm font-semibold">Ответы по персонам</h2>
          <p className="mb-4 text-xs text-muted-foreground">
            Разверните строку, чтобы увидеть обоснование с таймкодами
          </p>
          <PersonaAccordion personas={MOCK_PERSONAS} answers={answers} runId={run.id} />
        </section>
      </div>
    </>
  );
}
