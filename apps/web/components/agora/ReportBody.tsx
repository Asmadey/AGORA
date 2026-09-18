import type { ReactNode } from "react";

import { Chip, Metric, ScoreBar, TimecodeRef } from "@/components/agora/Primitives";
import { PersonaAccordion } from "@/components/agora/PersonaAccordion";
import { SurveyValuesChart } from "@/components/agora/SurveyValuesChart";
import { MetricProvenance } from "@/components/agora/MetricProvenance";
import { MetricInfo } from "@/components/agora/MetricInfo";
import { CRITERIA, CRITERIA_LABELS } from "@/lib/agora-types";
import { contributions, type MetricKey } from "@/lib/provenance";
import {
  matrixPairs,
  optionPairs,
  surveyBlocks,
  surveyQuestion,
} from "@/lib/report-survey";
import { showsSection, type ReportScope } from "@/lib/share-scope";
import type {
  AnswerView,
  ReportView,
  SurveyIndexKey,
  SurveyQuestionView,
  SurveyStats,
  SurveyView,
} from "@/lib/report-view";

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

/**
 * Доля процентами. Прочерк — «не считалось»: ноль означал бы, что вариант не
 * выбрал никто, а это другое утверждение.
 */
function pct(share: number | null): string {
  return share === null ? "—" : `${(share * 100).toFixed(0)}%`;
}

/**
 * Строка показателя: подпись и два числа — по всей аудитории и по срезу.
 *
 * Колонка среза у КАЖДОГО показателя — требование заказчика, а не украшение.
 * Поэтому она рисуется одной функцией на все типы вопросов: скопированная по
 * четырём веткам, она разошлась бы в половине из них при первой же правке.
 */
function SurveyRow({
  label,
  total,
  target,
  muted = false,
}: {
  label: string;
  total: string;
  target: string;
  muted?: boolean;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-baseline gap-x-4 py-[3px] text-sm">
      <span className={`min-w-0 truncate ${muted ? "text-slate" : ""}`} title={label}>
        {label}
      </span>
      <span className="w-14 text-right tabular-nums">{total}</span>
      <span className="w-14 text-right tabular-nums text-slate">{target}</span>
    </div>
  );
}

/**
 * Сколько человек стоит за числом.
 *
 * `n` — ответившие, `base` — опрошенные. Заказчик подписывает доли «в % от
 * опрошенных», а считаются они от ответивших: при полной анкете это одно и то
 * же, при пропусках — расходится вдвое. Выбирать знаменатель за читателя
 * нельзя, поэтому на экране стоят оба числа.
 */
function surveySize(stats: SurveyStats): string {
  return stats.base === null ? `${stats.n}` : `${stats.n} из ${stats.base}`;
}

/**
 * Один вопрос анкеты: заголовок, размеры охватов и числа по типу вопроса.
 *
 * Подавленный срез не рисуется прочерками молча — под вопросом стоит строка о
 * том, что срез меньше порога. Молчаливые прочерки в колонке читаются как сбой
 * расчёта, а это решение, принятое намеренно.
 */
function SurveyQuestionCard({
  question,
  targetLabel,
  minSegment,
}: {
  question: SurveyQuestionView;
  targetLabel: string;
  minSegment: number;
}) {
  // Колонка среза заполняется только из среза: сведение пар живёт в `lib`,
  // потому что подстановку «нет среза — покажем общее» разметка не сторожит
  // ничем, а выглядит такая подстановка как посчитанный срез.
  const options = optionPairs(question, question.total, question.target);
  const rows = matrixPairs(question, question.total, question.target);
  const unlabelled = [...options, ...rows].some((r) => !r.known);

  return (
    <div>
      <h4 className="text-sm font-medium">
        {question.number === null ? "" : `${question.number}. `}
        {question.label}
      </h4>
      {/*
        Размеры охватов стоят строкой над числами, а не в шапке колонок: «3 из
        3» не влезает в колонку шириной под «100 %», а обрезанное n читается
        как другое число.
      */}
      <p className="mt-0.5 text-[11px] text-slate">
        Ответили: {surveySize(question.total)} · в срезе «{targetLabel}»:{" "}
        {surveySize(question.target)}
      </p>
      <div className="mt-1 grid grid-cols-[1fr_auto_auto] gap-x-4 text-[11px] uppercase tracking-wide text-slate">
        <span>Показатель</span>
        <span className="w-14 text-right">Все</span>
        <span className="w-14 text-right normal-case tracking-normal">{targetLabel}</span>
      </div>

      <div className="mt-1 divide-y divide-hairline/60">
        {question.type === "scale" && (
          <>
            <SurveyRow
              label="Среднее"
              total={fmt(question.total.mean, 2)}
              target={fmt(question.target.mean, 2)}
            />
            <SurveyRow
              label="Доля 8–10"
              total={pct(question.total.topBox)}
              target={pct(question.target.topBox)}
            />
            {(question.total.groups ?? []).map((g) => (
              <SurveyRow
                key={g.id}
                label={`Баллы ${g.id}`}
                total={pct(g.share)}
                target={pct(
                  question.target.groups?.find((t) => t.id === g.id)?.share ?? null,
                )}
                muted
              />
            ))}
          </>
        )}

        {options.map((o) => (
          <SurveyRow
            key={o.id}
            label={o.label}
            total={pct(o.total)}
            target={pct(o.target)}
            muted={o.service}
          />
        ))}

        {rows.map((row) => (
          <div key={row.id} className="py-1">
            <p className="min-w-0 truncate text-xs text-slate" title={row.label}>
              {row.label}
            </p>
            {row.options.map((o) => (
              <SurveyRow
                key={o.id}
                label={o.label}
                total={pct(o.total)}
                target={pct(o.target)}
                muted={o.service}
              />
            ))}
          </div>
        ))}

        {question.type === "open" && (
          <SurveyRow
            label="Ответов в свободной форме"
            total={String(question.total.n)}
            target={String(question.target.n)}
          />
        )}
      </div>

      <div className="mt-1 space-y-0.5 text-[11px] text-slate">
        {question.target.belowThreshold && (
          <p>
            Срез «{targetLabel}»: {question.target.n} персон — меньше порога{" "}
            {minSegment}. Доли по нему не считались: доля по такой группе шагает
            слишком крупно, чтобы её можно было читать наравне с остальными.
          </p>
        )}
        {question.total.errors !== null && question.total.errors > 0 && (
          <p>
            Не разобрано по форме: {question.total.errors}. Такой ответ нарушил
            правило вопроса и в доли не идёт — он остаётся здесь числом, чтобы
            доля не выглядела посчитанной по всем.
          </p>
        )}
        {unlabelled && (
          <p>
            Подписи части вариантов в анкете заказчика не нашлись — на их месте
            стоят идентификаторы. Доли при этом посчитаны.
          </p>
        )}
        {question.type === "open" && (
          <p>Сами ответы стоят в карточках персон ниже.</p>
        )}
      </div>
    </div>
  );
}

/**
 * Секция «Ответы на анкету».
 *
 * Числа приходят посчитанными из `aggregate.survey` — это вывод `survey_tally`
 * воркера. Ни одного из них экран не считает сам: вторая формула разошлась бы с
 * первой молча, и два числа в одном отчёте отвечали бы на один вопрос по-разному.
 */
function SurveySection({ survey }: { survey: SurveyView }) {
  const targetLabel = survey.audience.targetRange ?? "срез";
  const indices: { key: SurveyIndexKey; label: string; hint: string }[] = [
    {
      key: "satisfaction",
      label: "Удовлетворённость",
      hint: "среднее долей 8–10 по пяти критериям",
    },
    {
      key: "perception",
      label: "Восприятие тем",
      hint: "среднее максимумов «тема поднималась» по темам",
    },
    { key: "nps", label: "NPS по анкете", hint: "доля 9–10 минус доля 0–6" },
  ];

  return (
    <section>
      <h2 className="mb-1 text-sm font-semibold">Ответы на анкету</h2>
      <p className="mb-4 text-xs text-slate">
        У каждого показателя два числа: по всей аудитории и по срезу «{targetLabel}».
        Рядом с каждым — сколько персон ответили.
        {survey.excludedByQa > 0
          ? ` Из расчёта выбыло ответов по правилам проверки: ${survey.excludedByQa}.`
          : ""}
      </p>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        {indices.map((index) => {
          const value = survey.indices[index.key];
          return (
            <div key={index.key} className="rounded-lg border border-hairline bg-card p-4">
              <p className="text-xs uppercase tracking-wide text-slate">{index.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {pct(value.total)}
              </p>
              <p className="mt-1 text-xs text-slate">
                {targetLabel}: {pct(value.target)} · {index.hint}
              </p>
            </div>
          );
        })}
      </div>
      {/*
        Прочерк у индекса — это «не считался», и причина у него одна: вопросов,
        из которых он собирается, в анкете не было. Среднее по четырём
        критериям из пяти выглядит как среднее по пяти, и различить их в отчёте
        нечем, поэтому писатель при неполном наборе не считает вовсе.
      */}
      <p className="mb-4 text-[11px] text-slate">
        Прочерк у показателя означает, что вопросов, из которых он собирается, в
        этой анкете не было: при неполном наборе он не считается вовсе.
      </p>

      <div className="space-y-4">
        {surveyBlocks(survey).map((block) => (
          <div key={block.id} className="rounded-lg border border-hairline bg-card p-5">
            <h3 className="text-xs uppercase tracking-wide text-slate">{block.label}</h3>
            <div className="mt-4 space-y-5">
              {block.questions.map((q) => (
                <SurveyQuestionCard
                  key={q.id}
                  question={q}
                  targetLabel={targetLabel}
                  minSegment={survey.minSegment}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/*
        Состав аудитории порога не признаёт: городов в корпусе семь, и порог,
        осмысленный для сравнения средних, уничтожил бы сам разрез, который
        заказчик требует прямо.
      */}
      <div className="mt-4 rounded-lg border border-hairline bg-card p-5">
        <h3 className="text-xs uppercase tracking-wide text-slate">Состав аудитории</h3>
        <p className="mt-1 text-xs text-slate">
          Всего персон: {survey.audience.total} · в срезе «{targetLabel}»:{" "}
          {survey.audience.target}
        </p>
        <div className="mt-3 flex flex-wrap gap-[15px]">
          {survey.audience.breakdowns.map((dim) => (
            <div key={dim.key} className="w-[240px]">
              <h4 className="mb-1 text-xs uppercase tracking-wide text-slate">
                {dim.label}
              </h4>
              <dl className="space-y-1 text-sm text-slate">
                {dim.counts.map((row) => (
                  <Row key={row.value} label={row.value} value={String(row.personas)} />
                ))}
              </dl>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
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
}: ReportBodyProps) {
  const show = (section: Parameters<typeof showsSection>[1]) => showsSection(scope, section);

  /**
   * Вопрос 8 — «какие ценности стремились донести создатели проекта».
   *
   * Отдельной переменной, потому что он стоит в панели показателей плиткой, а
   * не только в разделе анкеты: это ответ про материал, и место ему рядом с
   * остальными числами о материале.
   */
  const donatedValues = view.survey ? surveyQuestion(view.survey, 8) : null;

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
  /**
   * Содержимое попапа у показателя: шкала, обоснование, список ответов.
   *
   * Собрано здесь, а не в примитиве: примитив не должен знать ни про
   * происхождение чисел, ни про вербатимы. Он отводит место, попап наполняет
   * страница.
   */
  const info = (
    label: string,
    scale: string | null,
    rationale: string | null,
    provenance: ReactNode,
  ) =>
    scale || rationale || provenance ? (
      <MetricInfo label={label}>
        {scale && <p className="text-xs uppercase tracking-wide text-slate">{scale}</p>}
        {rationale && (
          <p className="mt-3 text-sm leading-relaxed text-foreground/90">{rationale}</p>
        )}
        {provenance}
      </MetricInfo>
    ) : undefined;

  const origin = (metric: MetricKey, reported: number | null) =>
    show("personas") ? (
      <MetricProvenance
        provenance={contributions(metric, answers)}
        reported={reported}
        total={audienceSize}
        open
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
        {/*
          Сводные метрики.

          Четыре величины, отвечающие на вопрос «как приняли материал», собраны
          в один блок: каждая в своей рамке читалась как отдельный сюжет.
          Пояснение к каждой — в попапе по значку, а не раскрытием под числом:
          раскрытие дёргало высоту всего ряда.
        */}
        <section className="space-y-3">
          <div className="rounded-lg border border-hairline bg-card p-4">
            <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2 xl:grid-cols-4">
              <Metric
                label="Общее впечатление"
                value={fmt(view.scores.overall_impression, 1)}
                hint="из 10"
                info={info("Общее впечатление", "из 10", null,
                  origin("overall_impression", view.scores.overall_impression))}
              />
              {/* Шкала подписана намеренно. NPS лежит в −100…+100, и «−86» без
                  подписи читается как ошибка расчёта, а не как «почти все
                  критики». Рядом — среднее по шкале 1–10: оно отвечает на
                  следующий вопрос читателя, «насколько всё-таки плохо». Одно
                  другое не заменяет: NPS чувствителен к поляризации, среднее —
                  нет. */}
              <Metric
                label="NPS"
                value={fmt(view.nps, 0)}
                hint="промоутеры минус критики"
                info={info("NPS", "промоутеры минус критики", view.rationales.nps,
                  origin("nps", view.nps))}
                tone={view.nps === null ? undefined : view.nps < 0 ? "bad" : view.nps > 30 ? "good" : "warn"}
              />
              <Metric
                label="Готовы рекомендовать"
                value={fmt(view.recommendation, 1)}
                hint="среднее по шкале 1–10"
                info={info("Готовы рекомендовать", "среднее по шкале 1–10", null,
                  origin("recommendation", view.recommendation))}
                tone={
                  view.recommendation === null
                    ? undefined
                    : view.recommendation < 5 ? "bad" : view.recommendation >= 8 ? "good" : "warn"
                }
              />
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            {/*
              Просмотр — одним блоком по просьбе владельца.

              «Досмотрят до конца» и «Досмотрено» остаются ДВУМЯ величинами, и
              это не придирка: первая считается по retention_intent, который
              категориален и процента просмотра не даёт; вторая приходит из
              шкального вопроса анкеты и без него честно пуста. Свести их в одно
              число значило бы выдумать данные.
            */}
            <div className="rounded-lg border border-hairline bg-card p-4">
              <p className="mb-4 text-xs uppercase tracking-wide text-slate">Просмотр</p>
              <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
                <Metric
                  label="Досмотрят до конца"
                  value={view.retentionRate === null ? "—" : `${view.retentionRate.toFixed(0)}%`}
                  hint="намерение досмотреть"
                  info={info("Досмотрят до конца", "доля намеревающихся досмотреть", null,
                    origin("retention", view.retentionRate))}
                  tone={view.retentionRate === null ? undefined : view.retentionRate < 70 ? "warn" : "good"}
                />
                {/*
                  Карточки нет вовсе, когда доли просмотра не спрашивали.

                  Здесь стояло «—» с подписью «в анкете не было вопроса о доле
                  просмотра». Пока вопрос был обязательным, прочерк означал
                  сбой и его стоило показывать. С 17.09.2026 обязательная
                  анкета — пятнадцать вопросов заказчика, доли просмотра среди
                  них нет, и прочерк стоял бы в КАЖДОМ отчёте.

                  Постоянный прочерк читается как «посчитать не смогли», а не
                  как «не спрашивали», и заказчик первым делом спросит, что
                  сломалось. Вопрос остаётся доступным: добавив его в анкету
                  своими руками, владелец возвращает и карточку.
                */}
                {view.watchedShare !== null && (
                  <Metric
                    label="Досмотрено"
                    value={`${view.watchedShare.toFixed(0)}%`}
                    hint="средняя доля просмотренного"
                    info={info("Досмотрено", "средняя доля просмотренного",
                      view.rationales.watched_share, origin("watched_share", view.watchedShare))}
                    tone={view.watchedShare < 60 ? "warn" : "good"}
                  />
                )}
              </div>
            </div>

            {/*
              На этом месте стоял график ценностей АУДИТОРИИ — сколько персон
              несут каждую из семнадцати. Он занял место карточки «Модель
              зрения» 16.09.2026 и уступил место вопросу 8 по решению владельца
              17.09.2026.

              Замена, а не соседство: две похожие плитки рядом читались бы как
              одно и то же число, посчитанное дважды. Разница в том, ЧТО они
              описывают. Ценности аудитории — свойство сгенерированных персон:
              они выпали при генерации и о материале не говорят ничего. Вопрос 8
              спрашивает, какие ценности аудитория увидела В МАТЕРИАЛЕ, и это
              ответ на вопрос исследования.

              `ValuesChart` при этом не удалён: состав ценностей набора остаётся
              свойством аудитории и нужен её реестру.

              Плитки нет вовсе, когда анкеты в прогоне не было: пустой график
              утверждал бы, что вопрос задавали и никто не ответил.
            */}
            {donatedValues && <SurveyValuesChart question={donatedValues} />}
          </div>
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

        {/*
          Ответы на анкету.

          Секции нет вовсе, когда `survey` пуст: это либо прогон без анкеты,
          либо отчёт, снятый до того, как агрегат научился её считать.
          Различить их по отчёту нечем, а пустая секция утверждала бы, что
          анкету задавали и никто не ответил.
        */}
        {show("survey") && view.survey && <SurveySection survey={view.survey} />}

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
            Панель называет вещи своими именами. «Исключено из агрегата» — это
            ИТОГ, после переспроса: вердикты второго круга заменяют вердикты
            первого, поэтому «переспрошено 8, исключено 3» значит, что пять
            ответов вернулись годными.
            До 28.08.2026 здесь стояло «перегенерации ответов в системе нет».
            Это перестало быть правдой 19.08, когда переспрос заведён, — и
            текст пережил механизм на девять дней, потому что число
            переспрошенных до отчёта не доезжало и опровергнуть подпись было
            нечем. */}
        {show("qa") && view.qa && (
          <section className="rounded-lg border border-hairline bg-card p-6">
            <h2 className="text-sm font-semibold">Проверка ответов</h2>
            <p className="mt-0.5 text-xs text-slate">
              Отчёт построен на {view.sampleSize} ответах
              {view.qa.requestioned !== null && view.qa.requestioned > 0 &&
                ` · ${view.qa.requestioned} переспрошено`}
              {view.excludedByQa > 0 && ` · ${view.excludedByQa} исключено из агрегата`}
            </p>
            <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="text-xs text-slate">Проверено вердиктов</dt>
                <dd className="mt-0.5 text-lg tabular-nums">{view.qa.checked}</dd>
              </div>
              {/*
                `qa.flagged` — ВСЕ вердикты `regenerate`, любого источника.
                Из агрегата с 17.09.2026 выбывают только нарушившие
                детерминированное правило: вердикт судьи помечает карточку и не
                блокирует (см. `GATING_QA_SOURCES`). Подставлять сюда `flagged`
                значило бы печатать «33 исключено» там, где не исключён почти
                никто, — и числа в одной строке перестали бы сходиться.
              */}
              <div>
                <dt className="text-xs text-slate">Помечено проверкой</dt>
                <dd className="mt-0.5 text-lg tabular-nums">{view.qa.flagged}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate">Исключено из агрегата</dt>
                <dd className="mt-0.5 text-lg tabular-nums">{view.excludedByQa}</dd>
              </div>
              {view.qa.requestioned !== null && (
                <div>
                  <dt className="text-xs text-slate">Переспрошено</dt>
                  <dd className="mt-0.5 text-lg tabular-nums">{view.qa.requestioned}</dd>
                </div>
              )}
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
            {/* Что именно произошло с забракованными — тремя состояниями, а
                не одной формулировкой на все случаи (PRD §21.5). Молчание
                здесь читается как «QA ничего не делал», и владелец уже
                однажды так и прочитал: увидел три карточки из двенадцати и
                решил, что прогон ненастоящий. */}
            <p className="mt-5 text-xs leading-relaxed text-slate">
              {view.qa.requestioned === null ? (
                <>
                  Этот отчёт собран до того, как счётчик переспроса стал в него попадать,
                  поэтому сказать, переспрашивались ли забракованные ответы, по нему нельзя.
                  В прогонах после 28.08.2026 это видно числом.
                </>
              ) : view.qa.requestioned > 0 ? (
                <>
                  Забракованные ответы переспрашиваются один раз:
                  {" "}{view.qa.requestioned} переспрошено, из агрегата в итоге исключено{" "}
                  {view.qa.flagged}. Вторая отбраковка окончательна — ответ выбывает из
                  расчёта. Потолок числа попыток задаётся в настройках команды.
                </>
              ) : view.qa.flagged > 0 ? (
                <>
                  Забракованные ответы исключены из расчёта и не переспрашивались:
                  переспрос выключен в настройках команды либо его потолок равен нулю.
                </>
              ) : (
                <>
                  Забракованных ответов нет — переспрос не понадобился. Он запускается
                  на любой непустой отбраковке, в пределах потолка из настроек команды.
                </>
              )}
            </p>
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

        {/*
          Дисклеймер «результат — гипотезы, а не измерение» убран по решению
          владельца 18.09.2026: он стоял под каждым отчётом и потому перестал
          читаться. Поле `disclaimer` в модели представления осталось — его
          пишет воркер, и терять запись из документа отчёта ради того, чтобы
          не рисовать абзац, незачем.
        */}
    </div>
  );
}
