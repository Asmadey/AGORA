import Link from "next/link";
import { MessageCircle, RotateCcw } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { JsonTree } from "@/components/agora/JsonTree";
import {
  Chip,
  ScoreBar,
  StatCard,
  TimecodeRef,
} from "@/components/agora/Primitives";
import { DeleteRunButton } from "@/components/agora/DeleteRunButton";
import { PersonaAccordion } from "@/components/agora/PersonaAccordion";
import { Timeline } from "@/components/agora/Timeline";
import { ShareDialog } from "@/components/agora/ShareDialog";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { loadReport, loadReportPersonas } from "@/lib/server/reports";
import { getTask, taskNumber, loadRunTiming } from "@/lib/server/tasks";
import { safePresign } from "@/lib/server/content-pack";
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
  const timing = await withTenant(tenantId, (client) => loadRunTiming(client, id));
  // Номер — для человека, идентификатор — для ссылки. Заголовок «Исследование
  // e81feb92-97a2-43ad-8112-de7503699c60» нельзя ни произнести, ни запомнить, а
  // сослаться на прогон в разговоре нужно каждый день.
  const task = await withTenant(tenantId, (client) => getTask(client, id));
  const number = taskNumber(task?.seqNo ?? null);
  // Подпись живёт час: записанная в базу ссылка протухла бы к первому открытию.
  const videoUrl = task?.videoRef ? safePresign(task.videoRef) : null;

  return (
    <>
      <PageHeader
        title={number ? `Исследование ${number}` : `Исследование ${id}`}
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
            {/* Удаление стоит последним и красное: оно уносит отчёт, за который
                заплачено моделью, и отменить его нечем. Подтверждение — внутри
                кнопки, диалог здесь тяжелее задачи. */}
            <DeleteRunButton runId={id} variant="danger" />
          </>
        }
      />

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
        <section>
          <h2 className="mb-1 text-sm font-semibold">Материал</h2>
          <Timeline runId={id} />
        </section>

        {/*
          Отчёт в исходном виде (п. 20).

          Экран показывает выжимку — числа, вербатимы, точки риска. Всё
          остальное лежит в отчёте и до сих пор доставалось только скачиванием
          файла и открытием его в другом приложении. Дерево отвечает на вопрос
          «а что там ещё есть» на месте.

          Свёрнуто по умолчанию: это инструмент для разбора, а не часть чтения
          отчёта, и раскрытый по умолчанию он оттеснял бы выводы вниз.
        */}
        <details className="rounded-lg border border-hairline bg-card p-6">
          <summary className="cursor-pointer text-sm font-semibold">
            Отчёт в исходном виде
          </summary>
          <div className="mt-3">
            <JsonTree value={envelope.report as never} label="отчёт" />
          </div>
        </details>

        {/*
          Материалы прогона (п. 36).

          Расшифровка и отчёт — то, чем пользуются ВНЕ продукта: вставляют в
          презентацию, шлют монтажёру, ищут цитату. Пока их нельзя было забрать,
          каждый такой случай означал переписывание с экрана.

          Ссылка на ролик подписывается на час: она уедет в переписку и в
          историю браузера, и вечная ссылка на чужое видео из этой переписки уже
          не отзывается.
        */}
        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Материалы</h2>
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            <a
              href={`/api/tasks/${id}/transcript`}
              className="rounded-md border border-hairline px-3 py-1.5 transition-colors hover:bg-secondary"
            >
              Расшифровка · txt
            </a>
            <a
              href={`/api/tasks/${id}/report`}
              download={`report-${id}.json`}
              className="rounded-md border border-hairline px-3 py-1.5 transition-colors hover:bg-secondary"
            >
              Отчёт · json
            </a>
            {videoUrl && (
              <a
                href={videoUrl}
                className="rounded-md border border-hairline px-3 py-1.5 transition-colors hover:bg-secondary"
              >
                Исходный ролик
              </a>
            )}
          </div>
          {videoUrl && (
            <p className="mt-2 text-xs text-slate">
              Ссылка на ролик подписана на час — по истечении откройте страницу заново.
            </p>
          )}
        </section>

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
            tone={view.nps === null ? undefined : view.nps < 0 ? "bad" : view.nps > 30 ? "good" : "warn"}
          />
          <StatCard
            label="Готовы рекомендовать"
            value={fmt(view.recommendation, 1)}
            hint="среднее по шкале 1–10"
            tone={
              view.recommendation === null
                ? undefined
                : view.recommendation < 5 ? "bad" : view.recommendation >= 8 ? "good" : "warn"
            }
          />
          <StatCard
            label="Досмотрят до конца"
            value={view.retentionRate === null ? "—" : `${view.retentionRate.toFixed(0)}%`}
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
          <StatCard
            label="Время обработки"
            value={timing.totalSec === null ? "—" : formatDuration(timing.totalSec)}
            hint={
              timing.nodes.length > 0
                ? `${timing.nodes.length} этапов · дольше всего ${longestNode(timing.nodes)}`
                : "разбивка по этапам не записана"
            }
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
              {/*
                Измерения кладутся в две колонки, а не столбиком: «Пол» с двумя
                значениями занимал целую строку рядом с пустотой, хотя рядом
                стоял «Тип населённого пункта» такой же высоты.

                Самое широкое измерение (больше всего значений) растягивается на
                обе колонки, остальные встают парами. Правило по числу значений,
                а не по имени: список измерений задаётся данными прогона, и
                зашитый порядок разъехался бы на первой же анкете с другим
                срезом.
              */}
              {/*
                Все измерения в один ряд. Раньше стояли две колонки плюс правило
                «самое длинное измерение занимает обе», и из-за него «Пол» уезжал
                на второй ряд — читалось это как отдельный, менее важный разрез.
              */}
              <div className="grid gap-6 lg:grid-cols-3">
                {view.segments.map((dim) => (
                  <div key={dim.key}>
                    <h3 className="mb-2 text-xs uppercase tracking-wide text-slate">
                      {dim.label}
                    </h3>
                    <div className="grid gap-3 sm:grid-cols-2">
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

        {/* Проверка ответов.
            Панель называет вещи своими именами: «исключено из агрегата», а не
            «пересоздано». Перегенерации в системе нет — забракованный ответ
            выбывает из расчёта и не переспрашивается, и писать сюда «пересоздано
            0» значило бы обещать несуществующий механизм. */}
        {view.qa && (
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
        {view.asked.length > 0 && (
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
        <section>
          <h2 className="mb-1 text-sm font-semibold">Ответы по персонам</h2>
          <p className="mb-4 text-xs text-slate">
            Разверните строку, чтобы увидеть обоснование с таймкодами
            {envelope.audienceSize > answers.length &&
              ` · показаны первые ${answers.length} из ${envelope.audienceSize}`}
          </p>
          <PersonaAccordion answers={answers} runId={id} asked={view.asked} />
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

/** Секунды → «4 мин 12 с». Часы появляются только когда они есть. */
function formatDuration(sec: number): string {
  const total = Math.max(0, Math.round(sec));
  if (total < 60) return `${total} с`;
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  return h > 0 ? `${h} ч ${m} мин` : `${m} мин ${total % 60} с`;
}

/** Самый долгий этап — то, чем объясняется длительность прогона. */
function longestNode(
  nodes: { node: string; durationSec: number | null }[],
): string {
  const worst = nodes.reduce<{ node: string; durationSec: number | null } | null>(
    (best, n) =>
      n.durationSec !== null && (best === null || n.durationSec > (best.durationSec ?? 0))
        ? n
        : best,
    null,
  );
  return worst && worst.durationSec !== null
    ? `${worst.node} (${formatDuration(worst.durationSec)})`
    : "неизвестно";
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
