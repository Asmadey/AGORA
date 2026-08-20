import type { AnswerView } from "./report-view";
import type { Criterion } from "./agora-types";

/**
 * Происхождение числа: из каких ответов оно посчитано.
 *
 * ─── Зачем ────────────────────────────────────────────────────────────────
 * «NPS −10» — это результат, а не вывод. Проверить его до сих пор было нечем:
 * читатель либо верил числу, либо выгружал JSON и считал руками. Владелец
 * дважды за две недели решал, что прогон ненастоящий, — и оба раза ответ лежал
 * в данных, до которых с экрана было не добраться.
 *
 * Связь одна и всегда одного направления: **число → ответы → материал**.
 * Человек ничего не конструирует, он ходит по готовым связям — это и был
 * первый из трёх вариантов конструктора (docs/CONSTRUCTOR_OPTIONS.md), и его
 * выбрал владелец 20.08.2026.
 *
 * ─── Главное требование ───────────────────────────────────────────────────
 * Список обязан ВОСПРОИЗВОДИТЬ показанное число. Раскрытие, где сумма не
 * сходится с шапкой, хуже отсутствия раскрытия: оно превращает проверяемое
 * число в спорное, а разбираться с расхождением приходится тому, кто пришёл
 * за ответом на другой вопрос.
 *
 * Отсюда два следствия:
 *
 * 1. Формулы повторяют `agent_core/analytics/aggregate.py` буквально — включая
 *    границы NPS (9–10 и 1–6), выпадение затруднившихся из знаменателя досмотра
 *    и отбрасывание доли просмотра вне шкалы 0–100. Приблизительное повторение
 *    здесь хуже отсутствия: расхождение в десятую долю выглядит как ошибка
 *    расчёта, а не как разные правила округления.
 * 2. Забракованные QA ответы не считаются — в агрегате их тоже нет. Они
 *    остаются в списке карточек, и именно поэтому их надо отфильтровать здесь,
 *    а не надеяться, что вызывающий помнит.
 *
 * Само сравнение «посчитанное против показанного» делает экран: только там
 * известно, что написано в шапке. Модуль отдаёт `computed`, чтобы это сравнение
 * было возможным.
 */

export const METRICS = [
  "overall_impression",
  "plot",
  "acting",
  "music",
  "cinematography",
  "nps",
  "recommendation",
  "retention",
  "watched_share",
] as const;

export type MetricKey = (typeof METRICS)[number];

const LABELS: Record<MetricKey, string> = {
  overall_impression: "Общее впечатление",
  plot: "Сюжет",
  acting: "Актёрская игра",
  music: "Музыка",
  cinematography: "Операторская работа",
  nps: "NPS",
  recommendation: "Готовы рекомендовать",
  retention: "Досмотрят до конца",
  watched_share: "Досмотрено",
};

export function metricLabel(key: MetricKey): string {
  return LABELS[key];
}

export interface ContributionRow {
  personaId: string;
  personaName: string;
  initials: string;
  avatarHue: number;
  segmentLabel: string | null;
  /** Значение, которое эта персона внесла в метрику. */
  value: number;
  /** Как оно показывается: «8», «75 %», «Досмотрит». */
  display: string;
  /** Роль в формуле, если метрика делит ответы на группы (NPS). */
  group: string | null;
  verbatim: string | null;
  refs: { timecode: string; note: string }[];
}

export interface Provenance {
  metric: MetricKey;
  /** Словесная формула — что именно сделали с этими значениями. */
  formula: string;
  rows: ContributionRow[];
  /** Число, посчитанное по строкам ниже. null — считать нечего. */
  computed: number | null;
  /** Сколько ответов выбыло по QA: они видны в карточках, но не в числе. */
  excluded: number;
  /** Сколько ответов метрику не назвали: они в выборке есть, в числе — нет. */
  silent: number;
}

/** Округление до сотых — как в отчёте, где числа показываются с одним знаком. */
function round(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return round(values.reduce((a, b) => a + b, 0) / values.length);
}

/**
 * Намерение досмотреть → `continue` | `stop` | `unknown`.
 *
 * Повтор `retention_stance` из `agent_core/qa/checks.py`, включая порядок:
 * отрицание проверяется первым, потому что «не досмотрел бы» содержит и
 * «досмотр», и «не досм». Порядок здесь решает, в какую сторону будет ошибка.
 *
 * Две реализации одного правила — цена того, что это два рантайма. Разъехаться
 * они могут только вместе со словарём, а словарь закреплён миграцией 33.
 */
const STOP_MARKERS = ["выключ", "останов", "прекрат", "бросил", "не досм", "не стал смотреть"];
const CONTINUE_MARKERS = ["досмотр", "до конца", "продолж", "не отрыва"];

export function retentionStance(value: string | null | undefined): "continue" | "stop" | "unknown" {
  const text = (value ?? "").toLowerCase();
  if (!text) return "unknown";
  if (STOP_MARKERS.some((m) => text.includes(m))) return "stop";
  if (CONTINUE_MARKERS.some((m) => text.includes(m))) return "continue";
  return "unknown";
}

/** Значение метрики в одном ответе. null — ответ по этой метрике молчит. */
function valueOf(metric: MetricKey, a: AnswerView): number | null {
  switch (metric) {
    case "nps":
    case "recommendation":
      return a.nps;
    case "retention": {
      const stance = retentionStance(a.retentionIntent);
      if (stance === "unknown") return null;
      return stance === "continue" ? 1 : 0;
    }
    case "watched_share":
      // Вне шкалы — испорченный ответ, а не крайнее значение: модель могла
      // отдать долю единицей, и втянутая в среднее единица занижает досмотр на
      // порядок, оставаясь правдоподобной.
      return a.watchedShare !== null && a.watchedShare >= 0 && a.watchedShare <= 100
        ? a.watchedShare
        : null;
    default:
      return a.scores[metric as Criterion] ?? null;
  }
}

const NPS_PROMOTER_MIN = 9;
const NPS_DETRACTOR_MAX = 6;

function groupOf(metric: MetricKey, value: number): string | null {
  if (metric !== "nps") return null;
  if (value >= NPS_PROMOTER_MIN) return "промоутер";
  if (value <= NPS_DETRACTOR_MAX) return "критик";
  return "нейтрал";
}

function displayOf(metric: MetricKey, value: number): string {
  if (metric === "retention") return value === 1 ? "Досмотрит" : "Выключит";
  if (metric === "watched_share") return `${value.toFixed(0)} %`;
  return String(round(value));
}

export function contributions(metric: MetricKey, answers: AnswerView[]): Provenance {
  // Забракованные не участвуют — их нет и в агрегате. Считаем их отдельно,
  // чтобы экран мог сказать, куда они делись, вместо молчаливой пропажи.
  const surviving = answers.filter((a) => a.qaFlags.length === 0);
  const excluded = answers.length - surviving.length;

  const rows: ContributionRow[] = [];
  for (const a of surviving) {
    const value = valueOf(metric, a);
    if (value === null) continue;
    rows.push({
      personaId: a.personaId,
      personaName: a.personaName,
      initials: a.initials,
      avatarHue: a.avatarHue,
      segmentLabel: a.segmentLabel,
      value,
      display: displayOf(metric, value),
      group: groupOf(metric, value),
      verbatim: a.verbatim,
      refs: a.groundingRefs,
    });
  }
  rows.sort((x, y) => y.value - x.value);

  const values = rows.map((r) => r.value);
  let computed: number | null;
  let formula: string;

  if (metric === "nps") {
    const promoters = values.filter((v) => v >= NPS_PROMOTER_MIN).length;
    const detractors = values.filter((v) => v <= NPS_DETRACTOR_MAX).length;
    computed =
      values.length === 0 ? null : round(((promoters - detractors) * 100) / values.length);
    formula =
      values.length === 0
        ? "никто не назвал готовность рекомендовать"
        : `промоутеров ${promoters} (9–10) минус критиков ${detractors} (1–6), ` +
          `делённые на ${values.length} ответов`;
  } else if (metric === "retention") {
    const yes = values.filter((v) => v === 1).length;
    computed = values.length === 0 ? null : round((yes * 100) / values.length);
    formula =
      values.length === 0
        ? "намерение досмотреть не назвал никто"
        : `${yes} из ${values.length}, кто ответил определённо; ` +
          "затруднившиеся в знаменатель не идут";
  } else {
    computed = mean(values);
    formula =
      values.length === 0
        ? "эту величину не назвал никто"
        : `среднее по ${values.length} ответам`;
  }

  return {
    metric,
    formula,
    rows,
    computed,
    excluded,
    silent: surviving.length - rows.length,
  };
}
