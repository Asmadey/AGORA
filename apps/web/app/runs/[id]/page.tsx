import Link from "next/link";
import { MessageCircle, RotateCcw } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import {
  Chip,
  HypothesisNotice,
  ScoreBar,
  StatCard,
  TimecodeRef,
} from "@/components/agora/Primitives";
import { PersonaAccordion } from "@/components/agora/PersonaAccordion";
import { ShareDialog } from "@/components/agora/ShareDialog";
import { requireSession } from "@/lib/server/guard";
import { loadReport, loadReportPersonas } from "@/lib/server/reports";
import { parseAnswer, parseReport } from "@/lib/report-view";
import { CRITERIA, CRITERIA_LABELS } from "@/lib/agora-types";

/**
 * Экран отчёта (PRD §5.E, §6): агрегат и графики сверху, аккордеон по персонам снизу.
 *
 * Порядок блоков отвечает порядку вопросов пользователя: «сколько?» → «почему?» →
 * «кто именно так сказал?». Групповой синтез стоит выше персон, потому что решение
 * принимают по темам, а не по отдельным репликам.
 *
 * Данные читаются из Mongo, куда их кладёт воркер. До задачи #21 экран
 * рендерился из `lib/mock-data`, и это дефект, который не видно на скриншоте:
 * экран с моком и экран с данными отличаются только тем, откуда взялись цифры.
 *
 * Первая страница карточек грузится на сервере вместе с отчётом, остальные —
 * маршрутом `/api/tasks/[id]/report/personas`: при 500 персонах с перекрытием ×3
 * карточки весят два мегабайта, а первый экран показывает пять чисел в шапке.
 */

/** Сколько карточек рисовать сразу. Дальше — догрузка постранично. */
const FIRST_PAGE = 50;

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { tenantId, userId } = await requireSession();
  const session = { tenantId, userId };

  const envelope = await loadReport(session, id);

  // Отчёта нет — это не ошибка, а «ещё не готов» либо чужой прогон. Различать
  // их на экране нельзя: сообщение «прогон принадлежит другой команде»
  // подтверждает, что такой прогон существует.
  if (!envelope) {
    return (
      <div className="p-8">
        <p className="text-slate">
          Отчёт по этому прогону недоступен: он ещё не готов или принадлежит другой команде.{" "}
          <Link href={`/runs/${id}/progress`} className="underline underline-offset-4">
            Смотреть прогресс
          </Link>
        </p>
      </div>
    );
  }

  const view = parseReport(envelope.report);
  const { items } = await loadReportPersonas(session, id, { limit: FIRST_PAGE });
  const answers = items.map(parseAnswer);

  return (
    <>
      <PageHeader
        title="Отчёт по прогону"
        subtitle={
          `${envelope.audienceSize} ответов` +
          (view.replicationCount > 1 ? ` · перекрытие ×${view.replicationCount}` : "") +
          (view.excludedByQa > 0 ? ` · ${view.excludedByQa} исключено QA` : "")
        }
        actions={
          <>
            <Link
              href={`/runs/${id}/chat`}
              className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
            >
              <MessageCircle className="h-4 w-4" />
              Обсудить результаты
            </Link>
            <Link
              href={`/studies/new?rerun=${id}`}
              className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
            >
              <RotateCcw className="h-4 w-4" />
              Перезапустить
            </Link>
            <ShareDialog />
          </>
        }
      />

      <div className="space-y-8 p-8">
        <HypothesisNotice replication={view.replicationCount} />

        {/* Чего в отчёте не хватает и почему. Молчаливая деградация выглядит
            как полный отчёт, и отличить её можно только по коду. */}
        {view.degraded.length > 0 && (
          <section className="rounded-lg border border-warning/30 bg-warning-soft/60 p-5">
            <h2 className="text-sm font-semibold text-warning">Отчёт собран не полностью</h2>
            <ul className="mt-2 space-y-1 text-sm text-slate">
              {view.degraded.map((d) => (
                <li key={d}>— {d}</li>
              ))}
            </ul>
          </section>
        )}

        {/* Сводные метрики.
            «Досмотрят до конца» и «Досмотрено» — две разные величины, и стоят
            рядом намеренно. Первая считается по retention_intent: он
            категориален, и процента просмотра из него не выводится. Вторая
            приходит из шкального вопроса анкеты, и без него честно пуста. */}
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <StatCard
            label="Общее впечатление"
            value={fmt(view.scores.overall_impression, 1)}
            hint="из 10"
          />
          <StatCard
            label="NPS"
            value={fmt(view.nps, 0)}
            hint="доля промоутеров минус критиков"
            tone={view.nps === null ? undefined : view.nps < 0 ? "bad" : view.nps > 30 ? "good" : "warn"}
          />
          <StatCard
            label="Досмотрят до конца"
            value={view.retentionRate === null ? "—" : `${view.retentionRate.toFixed(0)}%`}
            hint="доля намеренных досмотреть"
            tone={view.retentionRate === null ? undefined : view.retentionRate < 70 ? "warn" : "good"}
          />
          <StatCard
            label="Досмотрено"
            value={view.watchedShare === null ? "—" : `${view.watchedShare.toFixed(0)}%`}
            hint={
              view.watchedShare === null
                ? "в анкете не было вопроса о доле просмотра"
                : "средняя доля просмотренного"
            }
            tone={view.watchedShare === null ? undefined : view.watchedShare < 60 ? "warn" : "good"}
          />
          <StatCard
            label="Эмоциональный индекс"
            value={fmt(view.emotionalIndex, 1)}
            hint="из 10"
          />
        </section>

        {/* Нарратив: главный текст отчёта */}
        {view.narrative.length > 0 && (
          <section className="rounded-lg border border-hairline bg-card p-6">
            <h2 className="mb-3 text-sm font-semibold">Что показало исследование</h2>
            <div className="space-y-3 text-sm leading-relaxed">
              {view.narrative.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
          </section>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Критерии */}
          <section className="rounded-lg border border-hairline bg-card p-6">
            <h2 className="text-sm font-semibold">Оценки по критериям</h2>
            {view.replicationCount > 1 && (
              <p className="mt-0.5 text-xs text-slate">
                Затемнённая зона на шкале — разброс между повторами
              </p>
            )}
            <div className="mt-5 space-y-4">
              {CRITERIA.map((c) => (
                <ScoreBar
                  key={c}
                  label={CRITERIA_LABELS[c]}
                  value={view.scores[c] ?? 0}
                  confidence={view.spread[c]}
                />
              ))}
            </div>
          </section>

          {/* Эмоции */}
          <section className="rounded-lg border border-hairline bg-card p-6">
            <h2 className="text-sm font-semibold">Преобладающие эмоции</h2>
            {view.topEmotions.length === 0 ? (
              <p className="mt-4 text-sm text-slate">Эмоции не названы.</p>
            ) : (
              <div className="mt-5 space-y-3">
                {view.topEmotions.map((e) => (
                  <div key={e.name} className="flex items-center gap-3">
                    <span className="w-36 shrink-0 text-sm text-slate">{e.name}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                      <div
                        className="h-full rounded-full bg-foreground/70"
                        style={{ width: `${e.pct}%` }}
                      />
                    </div>
                    <span className="w-10 shrink-0 text-right text-sm tabular-nums">
                      {e.pct.toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* Точки риска: где аудитория собиралась бросить */}
        {view.riskPoints.length > 0 && (
          <section className="rounded-lg border border-hairline bg-card p-6">
            <h2 className="text-sm font-semibold">Где собирались бросить</h2>
            <p className="mt-0.5 text-xs text-slate">
              Моменты, названные теми, кто не стал бы досматривать
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {view.riskPoints.map((p) => (
                <TimecodeRef
                  key={p.timecode}
                  timecode={p.timecode}
                  note={`${p.note} · ${p.personas} персон`}
                />
              ))}
            </div>
          </section>
        )}

        {/* Сегменты */}
        <section>
          <h2 className="mb-1 text-sm font-semibold">Срез по сегментам</h2>
          {!view.hasSegments ? (
            <p className="text-sm text-slate">
              Срез не считался: в ответах этого прогона нет полей аудитории. Он
              появится в прогонах, запущенных после обновления.
            </p>
          ) : (
            <>
              <p className="mb-4 text-xs text-slate">
                Показаны группы от {view.minSegmentPersonas} персон: средняя по меньшей
                группе неотличима на вид от средней по сотне, а держится на нескольких ответах
              </p>
              <div className="space-y-6">
                {view.segments.map((dim) => (
                  <div key={dim.key}>
                    <h3 className="mb-2 text-xs uppercase tracking-wide text-slate">
                      {dim.label}
                    </h3>
                    <div className="grid gap-3 md:grid-cols-3">
                      {dim.rows.map((row) => (
                        <div
                          key={row.value}
                          className="rounded-lg border border-hairline bg-card p-5"
                        >
                          <div className="flex items-baseline justify-between gap-2">
                            <Chip tone="solid">{row.value}</Chip>
                            <span className="text-2xl font-semibold tabular-nums">
                              {fmt(row.overall, 1)}
                            </span>
                          </div>
                          <dl className="mt-3 space-y-1 text-sm text-slate">
                            <Row label="NPS" value={fmt(row.nps, 0)} />
                            <Row
                              label="Досмотрят"
                              value={row.retentionRate === null ? "—" : `${row.retentionRate.toFixed(0)}%`}
                            />
                            <Row label="Персон" value={String(row.personas)} />
                          </dl>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {/* Скрытые группы названы поимённо: молча пропавший сегмент
                  читается как потерянные данные. */}
              {view.suppressedSegments.length > 0 && (
                <p className="mt-4 text-xs text-slate">
                  Скрыто как слишком малые:{" "}
                  {view.suppressedSegments
                    .map((s) => `${s.value} (${s.personas})`)
                    .join(", ")}
                </p>
              )}
            </>
          )}
        </section>

        {/* Групповой синтез */}
        {view.themes.length > 0 && (
          <section>
            <h2 className="mb-1 text-sm font-semibold">Групповой синтез</h2>
            <p className="mb-4 text-xs text-slate">
              Темы, по которым персоны сошлись или разошлись
            </p>
            <div className="space-y-3">
              {view.themes.map((t) => (
                <div
                  key={t.title}
                  className="rounded-lg border border-hairline bg-card p-5"
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 className="font-medium">{t.title}</h3>
                    <Chip tone={t.agreement === "раскол" ? "solid" : "muted"}>{t.agreement}</Chip>
                  </div>
                  {t.summary && (
                    <p className="mt-2 text-sm leading-relaxed text-slate">
                      {t.summary}
                    </p>
                  )}
                  <div className="mt-4 space-y-2">
                    {t.quotes.map((q, i) => (
                      <blockquote key={i} className="border-l-2 border-hairline pl-3 text-sm">
                        «{q.text}»
                        <span className="ml-2 text-xs text-slate">
                          — {q.persona}
                          {q.timecode && (
                            <span className="ml-1.5 font-mono text-brand-blue">{q.timecode}</span>
                          )}
                        </span>
                      </blockquote>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {(view.strengths.length > 0 || view.weaknesses.length > 0) && (
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-lg border border-success/30 bg-success/10 p-5">
                  <h3 className="text-sm font-semibold text-success">Сильные стороны</h3>
                  <ul className="mt-3 space-y-1.5 text-sm">
                    {view.strengths.map((s) => (
                      <li key={s} className="text-slate">— {s}</li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-lg border border-warning/30 bg-warning-soft/60 p-5">
                  <h3 className="text-sm font-semibold text-warning">Что проседает</h3>
                  <ul className="mt-3 space-y-1.5 text-sm">
                    {view.weaknesses.map((s) => (
                      <li key={s} className="text-slate">— {s}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </section>
        )}

        {/* Персоны */}
        <section>
          <h2 className="mb-1 text-sm font-semibold">Ответы по персонам</h2>
          <p className="mb-4 text-xs text-slate">
            Разверните строку, чтобы увидеть обоснование с таймкодами
            {envelope.audienceSize > answers.length &&
              ` · показаны первые ${answers.length} из ${envelope.audienceSize}`}
          </p>
          <PersonaAccordion answers={answers} runId={id} />
        </section>

        {view.disclaimer && (
          <p className="border-t border-hairline pt-6 text-xs leading-relaxed text-slate">
            {view.disclaimer}
          </p>
        )}
      </div>
    </>
  );
}

/** Прочерк, а не ноль: «не посчитано» и «посчитано, вышло ноль» — разные факты. */
function fmt(value: number | null, digits: number): string {
  return value === null ? "—" : value.toFixed(digits);
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt>{label}</dt>
      <dd className="tabular-nums text-foreground">{value}</dd>
    </div>
  );
}
