import type { ReactNode } from "react";

import { Chip, ScoreBar, StatCard, TimecodeRef } from "@/components/agora/Primitives";
import { PersonaAccordion } from "@/components/agora/PersonaAccordion";
import { MetricProvenance } from "@/components/agora/MetricProvenance";
import { CRITERIA, CRITERIA_LABELS } from "@/lib/agora-types";
import { contributions, type MetricKey } from "@/lib/provenance";
import { humanDuration } from "@/lib/progress-state";
import { showsSection, type ReportScope } from "@/lib/share-scope";
import type { AnswerView, ReportView } from "@/lib/report-view";

/**
 * Тело отчёта — одно на внутреннюю страницу и на публичную ссылку.
 *
 * ─── Почему компонент появился ────────────────────────────────────────────
 * Публичная страница была ВТОРОЙ реализацией отчёта, написанной от руки: пять
 * секций против двенадцати у внутренней. Из выбора «весь отчёт / только
 * сводка» на ней зависела ровно одна секция — «Темы», — поэтому оба режима
 * показывали сводку, и владелец справедливо счёл это дефектом переключателя.
 *
 * Дефект был не в переключателе. Две реализации одного экрана расходятся
 * молча: сравнить их можно, только открыв рядом, а рядом их никто не держит.
 * Дописать в копию недостающие семь секций значило бы завести расхождение
 * заново, только позже и тише.
 *
 * Поэтому рисовальщик один, а разница между страницами вынесена в три вещи:
 * область (`scope`), плеер и дерево сырого JSON — они приходят пропами, потому
 * что берутся разными путями. Внутренняя страница читает материал маршрутом
 * под сессией, публичная — под токеном ссылки.
 *
 * ─── Что НЕ входит в тело ─────────────────────────────────────────────────
 * Шапка с кнопками. «Поделиться», «Скачать», «Перезапустить», «Удалить» и чат
 * ведут в разделы, закрытые сессией: гостю они предлагали бы то, чего он не
 * может сделать. Шапку рисует каждая страница своей.
 */

export interface ReportBodyProps {
  view: ReportView;
  answers: AnswerView[];
  /** Сколько ответов в прогоне всего — карточек на странице может быть меньше. */
  audienceSize: number;
  /** Идентификатор прогона: по нему аккордеон догружает следующие страницы. */
  runId: string;
  /** Подпись про отбраковку QA рядом со списком персон. */
  qaNote: string | null;
  scope: ReportScope;
  /**
   * Материал: плеер и таймлайн. Проп, а не собственный `<Timeline>`, потому
   * что данные для него берутся под сессией на внутренней странице и под
   * токеном — на публичной.
   */
  timeline?: ReactNode;
  /** Дерево сырого отчёта. Только внутренняя страница: наружу оно не идёт. */
  rawReport?: ReactNode;
  /**
   * Длительность прогона. `null` на публичной странице — не «не записана», а
   * «не показываем»: карточка просто не рисуется, а прочерк утверждал бы, что
   * замера нет.
   */
  timing?: { totalSec: number | null; nodes: { node: string; durationSec: number | null }[] } | null;
}

/** Виды проверки QA в человеческих словах. Ключи — из agent_core/qa/run.py. */
const QA_KINDS: Record<string, string> = {
  consistency: "Противоречия внутри ответа",
  grounding: "Ссылки на материал",
  diversity: "Однообразие ответов",
};

/** Источник вердикта: правило считает код, судью спрашивает модель. */
const QA_SOURCES: Record<string, string> = {
  rule: "правило",
  judge: "судья",
  escalated: "судья после эскалации",
};

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

/** Самый долгий этап — то, чем объясняется длительность прогона. */
function longestNode(nodes: { node: string; durationSec: number | null }[]): string {
  const worst = nodes.reduce<{ node: string; durationSec: number | null } | null>(
    (best, n) =>
      n.durationSec !== null && (best === null || n.durationSec > (best.durationSec ?? 0))
        ? n
        : best,
    null,
  );
  return worst && worst.durationSec !== null
    ? `${worst.node} (${humanDuration(worst.durationSec)})`
    : "неизвестно";
}

export function ReportBody({
  view,
  answers,
  audienceSize,
  runId,
  qaNote,
  scope,
  timeline,
  rawReport,
  timing = null,
}: ReportBodyProps) {
  const show = (section: Parameters<typeof showsSection>[1]) => showsSection(scope, section);

  /**
   * Происхождение числа: раскрытие под метрикой ведёт к ответам, из которых
   * она посчитана, а оттуда таймкодом — в плеер.
   *
   * Считается по карточкам, которые уже на странице, и сверяется с числом из
   * шапки: при аудитории больше первой страницы они разойдутся, и раскрытие
   * скажет об этом само. Молчаливое расхождение читалось бы как ошибка расчёта.
   *
   * В сводке раскрытия нет: оно показывает вербатим ответов, то есть сырьё.
   */
  const origin = (metric: MetricKey, reported: number | null) =>
    show("personas") ? (
      <MetricProvenance
        provenance={contributions(metric, answers)}
        reported={reported}
        total={audienceSize}
      />
    ) : undefined;

  return (
    <div className="space-y-8 p-8">
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

        {/* Разбор материала: плеер и таймлайн — первым, сразу под шапкой.
            Прежде он стоял ниже чисел, и порядок чтения был «сколько → что
            видела персона». На практике читатель начинает с ролика: числа без
            материала не с чем сопоставить, а ссылку персоны на момент нельзя
            проверить, не посмотрев этот момент. Теперь сначала «что именно
            видели», потом «сколько», потом «кто что сказал». */}
        {show("material") && (
          <section>
            <h2 className="mb-1 text-sm font-semibold">Материал</h2>
            {timeline}
          </section>
        )}

        {rawReport}

        {/* Происхождение числа: раскрытие под каждой метрикой ведёт к ответам
            персон, из которых она посчитана, а оттуда — таймкодом в плеер.
            Связь одного направления: число → ответы → материал. */}
        {/* Сводные метрики.
            «Досмотрят до конца» и «Досмотрено» — две разные величины, и стоят
            рядом намеренно. Первая считается по retention_intent: он
            категориален, и процента просмотра из него не выводится. Вторая
            приходит из шкального вопроса анкеты, и без него честно пуста. */}
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Общее впечатление"
            value={fmt(view.scores.overall_impression, 1)}
            hint="из 10"
            provenance={origin("overall_impression", view.scores.overall_impression)}
          />
          {/* Шкала подписана намеренно. NPS лежит в −100…+100, и «−86» без
              подписи читается как ошибка расчёта, а не как «почти все критики».
              Рядом — среднее по той же шкале 1–10: оно отвечает на следующий
              вопрос читателя, «насколько всё-таки плохо». Одно другое не
              заменяет: NPS чувствителен к поляризации, среднее — нет. */}
          <StatCard
            label="NPS"
            value={fmt(view.nps, 0)}
            hint="промоутеры минус критики"
            rationale={view.rationales.nps}
            provenance={origin("nps", view.nps)}
            tone={view.nps === null ? undefined : view.nps < 0 ? "bad" : view.nps > 30 ? "good" : "warn"}
          />
          <StatCard
            label="Готовы рекомендовать"
            value={fmt(view.recommendation, 1)}
            hint="среднее по шкале 1–10"
            provenance={origin("recommendation", view.recommendation)}
            tone={
              view.recommendation === null
                ? undefined
                : view.recommendation < 5 ? "bad" : view.recommendation >= 8 ? "good" : "warn"
            }
          />
          <StatCard
            label="Досмотрят до конца"
            value={view.retentionRate === null ? "—" : `${view.retentionRate.toFixed(0)}%`}
            provenance={origin("retention", view.retentionRate)}
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
            rationale={view.rationales.watched_share}
            provenance={origin("watched_share", view.watchedShare)}
            tone={view.watchedShare === null ? undefined : view.watchedShare < 60 ? "warn" : "good"}
          />
          <StatCard
            label="Эмоц. индекс"
            value={fmt(view.emotionalIndex, 1)}
            hint="из 10"
            rationale={view.rationales.emotional_index}
          />
          {/* Прочерк, а не ноль: прогоны до появления замеров не знают своей
              длительности, и «0 с» утверждало бы, что обработка была мгновенной. */}
          {/* Какими моделями считался прогон. Отдельной карточкой, а не
              строкой в подвале: доля отбраковок и тон ответов зависят от
              модели не меньше, чем от материала, и сравнивать два отчёта, не
              зная модели, значит сравнивать не то. */}
          {view.modelsUsed && (
            <StatCard
              label="Модель зрения"
              value={view.modelsUsed.vision || "—"}
              hint={
                view.modelsUsed.judge && view.modelsUsed.judge !== view.modelsUsed.text
                  ? `рассуждение ${view.modelsUsed.text} · судья ${view.modelsUsed.judge}`
                  : `рассуждение и проверка ${view.modelsUsed.text}`
              }
            />
          )}
          {/* Длительность прогона. Карточки нет вовсе, когда замер не передан:
              прочерк здесь означает «замера нет», а на публичной странице
              причина другая — время просто не показывают. Прочерк с чужим
              смыслом хуже отсутствующей карточки. */}
          {timing && (
            <StatCard
              label="Время обработки"
              value={timing.totalSec === null ? "—" : humanDuration(timing.totalSec)}
              hint={
                timing.nodes.length > 0
                  ? `${timing.nodes.length} этапов · дольше всего ${longestNode(timing.nodes)}`
                  : "разбивка по этапам не записана"
              }
            />
          )}
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
            <p className="mt-0.5 text-xs text-slate">
              {view.replicationCount > 1
                ? "Затемнённая зона на шкале — разброс между повторами"
                : "Перекрытие равно 1: разброс между повторами не измерялся"}
            </p>
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
        {show("riskPoints") && view.riskPoints.length > 0 && (
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

        {show("segments") && (
          <section>
            <h2 className="mb-1 text-sm font-semibold">Срез по сегментам</h2>
            {!view.hasSegments ? (
              <p className="text-sm text-slate">
                Срез не считался: в ответах этого прогона нет полей аудитории. Он
                появится в прогонах, запущенных после обновления.
              </p>
            ) : (
              <>
                {/*
                  Все плашки на одном уровне и с ОДИНАКОВЫМ зазором в 15 пикселей —
                  и между значениями внутри измерения, и между самими измерениями.

                  Сетка из равных колонок здесь не годится: у «Возраста» одно
                  значение, у «Пола» два, и колонка под одну плашку оставляла
                  пустоту шириной со вторую. Зазор при этом переставал быть
                  зазором — глаз читал его как границу раздела.

                  Поэтому ряд, а не сетка: плашки одной ширины идут подряд и
                  переносятся, когда кончается строка. Подпись измерения стоит над
                  своей группой и уезжает вместе с ней.
                */}
                <div className="flex flex-wrap gap-[15px]">
                  {view.segments.map((dim) => (
                    <div key={dim.key}>
                      <h3 className="mb-2 text-xs uppercase tracking-wide text-slate">
                        {dim.label}
                      </h3>
                      <div className="flex flex-wrap gap-[15px]">
                        {dim.rows.map((row) => (
                          <div
                            key={row.value}
                            className="w-[240px] rounded-lg border border-hairline bg-card p-5"
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
        )}

        {/* Групповой синтез */}
        {show("synthesis") && view.themes.length > 0 && (
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

        {/* Проверка ответов.
            Панель называет вещи своими именами: «исключено из агрегата», а не
            «пересоздано». Перегенерации в системе нет — забракованный ответ
            выбывает из расчёта и не переспрашивается, и писать сюда «пересоздано
            0» значило бы обещать несуществующий механизм. */}
        {show("qa") && view.qa && (
          <section className="rounded-lg border border-hairline bg-card p-6">
            <h2 className="text-sm font-semibold">Проверка ответов</h2>
            <p className="mt-0.5 text-xs text-slate">
              Отчёт построен на {view.sampleSize} ответах
              {view.qa.flagged > 0 && ` · ${view.qa.flagged} исключено из агрегата`}
            </p>
            <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="text-xs text-slate">Проверено вердиктов</dt>
                <dd className="mt-0.5 text-lg tabular-nums">{view.qa.checked}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate">Исключено из агрегата</dt>
                <dd className="mt-0.5 text-lg tabular-nums">{view.qa.flagged}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate">Ушло на эскалацию</dt>
                <dd className="mt-0.5 text-lg tabular-nums">{view.qa.escalated}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate">Судья не ответил</dt>
                <dd className="mt-0.5 text-lg tabular-nums">{view.qa.judgeFailures}</dd>
              </div>
            </dl>
            {(view.qa.byKind.length > 0 || view.qa.bySource.length > 0) && (
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                {view.qa.byKind.length > 0 && (
                  <div>
                    <p className="text-xs text-slate">По видам проверки</p>
                    <ul className="mt-1 space-y-0.5 text-sm">
                      {view.qa.byKind.map((row) => (
                        <li key={row.kind}>
                          {QA_KINDS[row.kind] ?? row.kind} — {row.count}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {view.qa.bySource.length > 0 && (
                  <div>
                    <p className="text-xs text-slate">Кто забраковал</p>
                    <ul className="mt-1 space-y-0.5 text-sm">
                      {view.qa.bySource.map((row) => (
                        <li key={row.source}>
                          {QA_SOURCES[row.source] ?? row.source} — {row.count}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            <p className="mt-5 text-xs leading-relaxed text-slate">
              Забракованный ответ исключается из расчёта, а не переспрашивается:
              перегенерации ответов в системе нет.
            </p>
          </section>
        )}

        {/*
          Заданные вопросы.

          Секция отвечает на вопрос, который иначе проверяется только чтением
          кода: получила ли персона анкету. Список собран воркером из готовой
          строки промпта — то есть из того, что действительно ушло в модель, а
          не из анкеты в базе, которую после прогона можно отредактировать.
        */}
        {show("asked") && view.asked.length > 0 && (
          <section>
            <h2 className="mb-1 text-sm font-semibold">Заданные вопросы</h2>
            <p className="mb-4 text-xs text-slate">
              {view.asked.length}{" "}
              {view.asked.length === 1 ? "вопрос" : view.asked.length < 5 ? "вопроса" : "вопросов"}{" "}
              в том виде, в каком их получила каждая персона
            </p>
            <ol className="space-y-2 text-sm">
              {view.asked.map((q, index) => (
                <li key={q.id} className="flex gap-3">
                  <span className="w-6 shrink-0 text-right tabular-nums text-slate">
                    {index + 1}.
                  </span>
                  <span className="flex-1">
                    {q.label}
                    <span className="ml-2 text-xs text-slate">{q.type}</span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {/* Персоны */}

        {show("personas") && (
          <section>
            <h2 className="mb-1 text-sm font-semibold">Ответы по персонам</h2>
            {/*
              Подпись про отбраковку стоит здесь, а не только в шапке.

              Владелец запустил двенадцать персон, увидел три и решил, что прогон
              ненастоящий. Девять забраковал QA — законная работа проверки, — но
              число исключённых показывалось мелким шрифтом в подписи заголовка,
              далеко от самого списка. Там, где его ищут, его не было.
            */}
            <p className="mb-4 text-xs text-slate">
              Разверните строку, чтобы увидеть обоснование с таймкодами
              {view.excludedByQa === 0 && audienceSize > answers.length &&
                ` · показаны первые ${answers.length} из ${audienceSize}`}
            </p>
            {qaNote && (
              <p className="mb-4 rounded-md border border-warning/30 bg-warning-soft/60 px-4 py-3 text-xs leading-relaxed">
                {qaNote}
              </p>
            )}
            <PersonaAccordion answers={answers} runId={runId} asked={view.asked} />
          </section>
        )}

        {view.disclaimer && (
          <p className="border-t border-hairline pt-6 text-xs leading-relaxed text-slate">
            {view.disclaimer}
          </p>
        )}
    </div>
  );
}
