import { CRITERIA, type Criterion } from "./agora-types.ts";

/**
 * Разбор отчёта в то, что рисует экран (задача #21).
 *
 * Отдельный модуль, а не разбор по месту в page.tsx, по двум причинам. Первая:
 * отчёт приходит из Mongo как `Record<string, unknown>` — воркер пишет его
 * питоновскими именами полей, и превращение `snake_case` в модель экрана обязано
 * быть в одном месте, иначе следующий экран разберёт его чуть иначе. Вторая:
 * это чистые функции без сети и без сессии, поэтому их поведение на неполных
 * данных проверяется тестом, а не открытием страницы.
 *
 * Сквозное правило: недостающее поле даёт `null`, а не `0` и не пустую строку.
 * Ноль на экране — это утверждение «измерено, вышло ноль», и отличить его от
 * «не измеряли» пользователь не может.
 */

export interface SegmentRow {
  value: string;
  overall: number | null;
  nps: number | null;
  retentionRate: number | null;
  personas: number;
}

export interface SegmentDimension {
  key: string;
  label: string;
  rows: SegmentRow[];
}

export interface SuppressedSegment {
  dimension: string;
  value: string;
  personas: number;
}

export interface ReportView {
  scores: Record<Criterion, number | null>;
  /** Разброс между повторами. Пусто при replication_count = 1 — разбрасываться нечему. */
  spread: Partial<Record<Criterion, { mean: number; min: number; max: number; stdev: number }>>;
  nps: number | null;
  retentionRate: number | null;
  /** Средняя доля просмотренного. null — в анкете не было вопроса о ней. */
  watchedShare: number | null;
  emotionalIndex: number | null;
  /**
   * Обоснования под числами: почему NPS такой, почему досмотр такой.
   *
   * Пустой словарь означает «модель не отвечала», отсутствие ключа — «по этой
   * метрике оснований в ответах не нашлось». Оба случая честнее выдуманной
   * фразы: по выдуманной примут решение.
   */
  rationales: Record<string, string>;
  topEmotions: { name: string; pct: number }[];
  sampleSize: number;
  excludedByQa: number;
  replicationCount: number;
  replicationStability: number | null;
  narrative: string[];
  themes: { title: string; agreement: string; summary: string; quotes: Quote[] }[];
  strengths: string[];
  weaknesses: string[];
  riskPoints: { timecode: string; note: string; personas: number }[];
  segments: SegmentDimension[];
  suppressedSegments: SuppressedSegment[];
  minSegmentPersonas: number;
  /** null — разрез не считали (в ответах не было среза DNA). */
  hasSegments: boolean;
  /**
   * Вопросы, которые персоны действительно получили в промпте.
   *
   * Не анкета из базы: анкету можно отредактировать после прогона, и тогда
   * экран показывал бы не то, что спрашивали. Воркер собирает этот список из
   * готовой строки промпта — то есть из того, что ушло в модель.
   *
   * Пусто у прогонов до появления поля и у прогонов без анкеты (они законны:
   * пять базовых критериев живут в формате ответа). Различать эти два случая
   * экран не пытается — он просто не показывает секцию.
   */
  asked: AskedQuestion[];
  /**
   * Модели, которыми считался прогон: рассуждение, зрение, судья.
   *
   * Пустой объект — прогон сделан до того, как выбор моделей стал настройкой.
   * Отличать это от «модель неизвестна» нужно: первое означает «тогда была одна
   * на всех», второе — что запись потерялась.
   */
  modelsUsed: { text: string; vision: string; judge: string } | null;
  /**
   * Средняя готовность рекомендовать, 1–10.
   *
   * Рядом с NPS, а не вместо него. NPS — доля промоутеров минус доля критиков,
   * он лежит в −100…+100 и при почти сплошных критиках честно даёт −86. Число
   * без подписи шкалы читается как ошибка расчёта, а среднее по той же шкале
   * 1–10 отвечает на вопрос «а насколько всё-таки плохо».
   */
  recommendation: number | null;
  /**
   * Сводка QA: сколько ответов проверено, сколько переспрошено и сколько
   * осталось исключённым из агрегата.
   *
   * `flagged` — это ИТОГ, после переспроса: вердикты второго круга заменяют
   * вердикты первого. Поэтому «переспрошено 8, исключено 3» — нормальная
   * пара чисел, а не противоречие: пять ответов вернулись годными.
   *
   * `requestioned` появился 28.08.2026. До него число жило в состоянии
   * конвейера и до отчёта не доезжало, а экран утверждал, что переспроса в
   * системе нет, — механизм работал с 19.08 и был описан в PRD.
   */
  qa: {
    checked: number;
    flagged: number;
    byKind: { kind: string; count: number }[];
    bySource: { source: string; count: number }[];
    escalated: number;
    judgeFailures: number;
    /**
     * Сколько ответов переспрошено. `null` — отчёт собран до 28.08.2026 и поля
     * не содержит: это «неизвестно», а не «ноль».
     *
     * Различать обязательно. Прогон 0051 шёл 20.08, когда переспрос уже
     * работал; сказать по его отчёту «переспрос был выключен» — это догадка,
     * выданная за факт, ровно того же рода, что и прежняя подпись «механизма
     * нет».
     */
    requestioned: number | null;
  } | null;
  disclaimer: string | null;
  degraded: string[];
  /**
   * Посчитанная анкета: `aggregate.survey`, он же результат `survey_tally`.
   *
   * `null` — анкеты в прогоне не было ЛИБО отчёт снят до того, как агрегат
   * научился её считать. Различать эти два случая по отчёту нечем, и пустая
   * секция утверждала бы, что анкету задавали, а ответов нет.
   */
  survey: SurveyView | null;
}

/**
 * Анкета, посчитанная воркером.
 *
 * Форма повторяет вывод `survey_tally`
 * (`services/agent-core/agent_core/analytics/survey_stats.py`) один в один:
 * здесь только переименование питоновских ключей и приведение словарей к
 * спискам, чтобы порядок строк на экране не зависел от порядка обхода объекта.
 * Ни одного числа этот разбор не считает — вся арифметика живёт у писателя, и
 * вторая её копия разошлась бы с первой молча.
 */
export interface SurveyView {
  /** Вопросы по возрастанию номера; вопросы без номера — в конце. */
  questions: SurveyQuestionView[];
  /**
   * Интегральные показатели заказчика — доли, а не проценты: 0.6667 значит
   * 66,7 %. NPS здесь тоже доля (−1…+1), а не привычные −100…+100: писатель
   * считает его вычитанием долей, и домножение на сто — дело экрана.
   */
  indices: Record<SurveyIndexKey, { total: number | null; target: number | null }>;
  audience: SurveyAudience;
  /**
   * Порог показа долей в срезе. Ниже него писатель убирает числа, оставляя
   * размер: доля по группе из пяти шагает по двадцать процентных пунктов и
   * выглядит на экране так же уверенно, как доля по сотне.
   */
  minSegment: number;
  /** Сколько ответов выбыло по детерминированным правилам QA. */
  excludedByQa: number;
}

export type SurveyIndexKey = "satisfaction" | "perception" | "nps";

export interface SurveyQuestionView {
  id: string;
  /** Номер в анкете заказчика. `null` у вопросов, добавленных оператором. */
  number: number | null;
  /** `scale`, `single_choice`, `multi_choice`, `matrix_single`, `open`. */
  type: string;
  /** Блок заказчика: `b1`…`b6`. `null` — вопрос вне блоков. */
  block: string | null;
  label: string;
  total: SurveyStats;
  /** Тот же показатель по срезу «14–35». */
  target: SurveyStats;
}

/**
 * Состав аудитории. Порога не признаёт намеренно: городов в корпусе семь, и
 * порог, осмысленный для сравнения средних, уничтожил бы сам разрез.
 */
export interface SurveyAudience {
  total: number;
  target: number;
  /** Подпись среза, как её задал писатель: «14–35». */
  targetRange: string | null;
  breakdowns: { key: string; label: string; counts: { value: string; personas: number }[] }[];
}

/**
 * Один показатель по одному охвату.
 *
 * Заполнены поля, осмысленные для типа вопроса: у шкалы — `mean`, `topBox` и
 * `groups`, у выбора — `options` и `errors`, у матрицы — `rows`, у открытого —
 * `texts`. Остальные равны `null`, и это то же `null`, что у подавленного
 * среза: «не считалось». Ноль сюда не подставляется нигде.
 */
export interface SurveyStats {
  /** Сколько персон ответили на вопрос. */
  n: number;
  /**
   * Сколько персон в этом охвате опрашивали. Стоит рядом с `n`, потому что
   * заказчик подписывает доли «в % от опрошенных», а считаются они от
   * ОТВЕТИВШИХ: при полной анкете это одно число, при пропусках — два разных.
   */
  base: number | null;
  /** Срез меньше `minSegment`: числа не считались, размер остался. */
  belowThreshold: boolean;
  mean: number | null;
  /** Доля верхних баллов, 8–10. Доля, а не проценты. */
  topBox: number | null;
  /** Группы шкалы 9–10 / 7–8 / 0–6 в порядке писателя. */
  groups: { id: string; share: number }[] | null;
  /**
   * Доли по вариантам в порядке анкеты, включая невыбранные.
   *
   * Невыбранный вариант — ноль, а не пропавшая строка: исчезнувшая строка на
   * графике читается как «такого варианта не предлагали».
   */
  options: { id: string; share: number | null; count: number | null }[] | null;
  /** Сколько ответов выброшено как нарушившие форму вопроса. */
  errors: number | null;
  /** Ответы на открытый вопрос. */
  texts: string[] | null;
  /** Строки матрицы. У подавленного среза — `null`, а не пустой список. */
  rows: { id: string; themeId: string | null; stats: SurveyStats }[] | null;
}

export interface Quote {
  text: string;
  persona: string;
  timecode: string | null;
}

/**
 * Вопрос анкеты в том виде, в каком его ЗАДАЛИ персонам.
 *
 * Берётся из снимка `survey_asked` прогона, а не из анкеты на момент чтения
 * отчёта: анкету правят между прогонами, и показать сегодняшние вопросы под
 * вчерашними ответами значило бы соврать о том, что персону спрашивали.
 */
export interface AskedQuestion {
  id: string;
  label: string;
  type: string;
  /**
   * Ключ базового критерия, если вопрос базовый.
   *
   * Ответ на такой вопрос промпт кладёт в `scores`, а не в `survey_answers` —
   * без этого поля карточка ищет его не там и показывает «не ответила» под
   * нарисованным рядом баллом.
   */
  baseKey?: Criterion;
}

export interface AnswerView {
  personaId: string;
  personaName: string;
  initials: string;
  avatarHue: number;
  replication: number;
  segmentLabel: string | null;
  scores: Record<Criterion, number | null>;
  overall: number | null;
  retentionIntent: string | null;
  watchedShare: number | null;
  nps: number | null;
  emotions: string[];
  verbatim: string | null;
  groundingRefs: { timecode: string; note: string }[];
  /**
   * Замечания QA по этому ответу. Прежде здесь лежали строки, и в них доезжал
   * `verdict` — одно и то же слово «regenerate» на все забракованные ответы.
   */
  qaFlags: QaFlagView[];
  /**
   * Ответы на анкету, как их дала персона: ключ — идентификатор вопроса ЛИБО
   * его текст (промпт разрешает и то, и другое).
   *
   * Хранится сырым словарём, а не готовым списком: сопоставление с заданными
   * вопросами делает карточка, потому что только там известен порядок анкеты.
   * Собранный здесь список пришлось бы пересобирать при каждом изменении
   * анкеты, а он один на все карточки прогона.
   */
  surveyAnswers: Record<string, string>;
  /** Свободные ответы: почему такое впечатление, что запомнилось, о героях. */
  verbatims: Record<string, string>;
}

/**
 * Замечание QA по одному ответу — как его кладёт воркер (`qa/run.py`, `_verdict`).
 *
 * Поле называется `reasons`, во множественном числе: на прогоне 0091 у 33
 * флагов 66 причин, и первая из них не всегда главная.
 */
export interface QaFlagView {
  /** Что проверяли: `consistency`, `grounding`, `diversity`. */
  kind: string;
  /** Уверенность судьи, 0..1. У правил — 1, у судьи на 0091 — от 0.70 до 0.95. */
  confidence: number | null;
  /**
   * Причины словами. Пустой список значит «забраковано без объяснения» — это
   * возможно и это стоит показать, а не выбросить: исчезнувший флаг делает
   * забракованный ответ похожим на чистый.
   */
  reasons: string[];
  /**
   * Кто вынес вердикт: `rule`, `judge` или `escalated`.
   *
   * От этого зависит, выбывает ли ответ из агрегата. Детерминированные правила
   * ловят объективный брак — балл вне шкалы 1–10, таймкод за пределами
   * ролика, — и такой ответ в среднее не положишь. Вердикт судьи субъективен и
   * только помечает карточку: владелец решил 17.09.2026, что QA информирует, а
   * не блокирует. Граница держится в `analytics/aggregate.py` (`GATING_SOURCES`)
   * и здесь — списком `GATING_QA_SOURCES` ниже.
   *
   * Умолчание `rule`, а не `judge`: отчёты, снятые до появления поля, его не
   * содержат, и считать их субъективными значило бы пересчитать прежние
   * агрегаты иначе, чем их читали.
   */
  source: string;
}

/**
 * Источники вердикта, по которым ответ ВЫБЫВАЕТ из агрегата.
 *
 * Перечень повторяет `GATING_SOURCES` в `analytics/aggregate.py`. Два списка в
 * двух языках расходятся молча, поэтому их совпадение проверяет
 * `services/agent-core/tests/test_qa_gating_sources_agree.py`: он читает этот
 * файл и сравнивает составы. Комментарий здесь когда-то уже ссылался на
 * несуществующую проверку — ложная уверенность хуже её отсутствия.
 */
export const GATING_QA_SOURCES: ReadonlySet<string> = new Set(["rule"]);

/**
 * Подписи видов проверки. Незнакомый вид показывается как есть: судья может
 * завести новый раньше, чем сюда допишут перевод, и пропасть он не должен.
 */
const QA_KIND_LABELS: Record<string, string> = {
  consistency: "Согласованность",
  grounding: "Опора на материал",
  diversity: "Разнообразие",
};

export function qaKindLabel(kind: string): string {
  return QA_KIND_LABELS[kind] ?? kind;
}

const SEGMENT_LABELS: Record<string, string> = {
  age_group: "Возраст",
  geo: "Тип населённого пункта",
  gender: "Пол",
};

/** `"00:40 спор на кухне"` → таймкод и подпись. */
const REF = /^\s*(\d{1,2}:[0-5]\d(?::[0-5]\d)?)\s*(.*)$/;

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function obj(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/**
 * Словарь произвольных значений → словарь строк, годных для показа.
 *
 * Ответ на вопрос анкеты бывает числом (шкала), массивом (эмоции, ценности) и
 * логическим значением — тип задаёт вопрос, а не персона. Показывать их надо
 * все, поэтому приведение здесь, а не в разметке: `String(["интерес","скука"])`
 * дал бы «интерес,скука» без пробела, а `String({})` — «[object Object]».
 *
 * Пустые значения отбрасываются: пустая строка в карточке неотличима от
 * «вопрос задан, ответа нет», а это разные вещи.
 */
function flatten(source: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(source)) {
    if (value === null || value === undefined) continue;
    const text = Array.isArray(value)
      ? value.map((v) => String(v)).filter(Boolean).join(", ")
      : typeof value === "object"
        ? JSON.stringify(value)
        : String(value);
    if (text.trim()) out[key] = text;
  }
  return out;
}

/**
 * Цвет аватара выводится из идентификатора персоны, а не хранится.
 *
 * Персон в прогоне до пятисот, и держать для каждой поле ради оттенка — это
 * колонка в базе, которую надо мигрировать. Детерминированность важнее
 * равномерности: одна и та же персона обязана выглядеть одинаково на всех
 * экранах, иначе аватар перестаёт помогать её узнавать.
 */
export function avatarHue(personaId: string): number {
  let h = 0;
  for (let i = 0; i < personaId.length; i += 1) {
    h = (h * 31 + personaId.charCodeAt(i)) % 360;
  }
  return h;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean).slice(0, 2);
  return parts.map((w) => w[0]?.toUpperCase() ?? "").join("") || "?";
}

function scoresOf(source: Record<string, unknown>): Record<Criterion, number | null> {
  const out = {} as Record<Criterion, number | null>;
  for (const c of CRITERIA) out[c] = num(source[c]);
  return out;
}

/**
 * Сводка QA из отчёта. `null` — прогон сделан до её появления.
 *
 * `null`, а не нули: «проверено 0» и «не знаем, проверялось ли» — разные факты,
 * и первый на экране означал бы, что судья не посмотрел ни одного ответа.
 */
function qaOf(value: unknown): ReportView["qa"] {
  const raw = obj(value);
  if (Object.keys(raw).length === 0) return null;

  const counts = (source: unknown, key: "kind" | "source") =>
    Object.entries(obj(source))
      .map(([name, count]) => ({ [key]: name, count: num(count) ?? 0 }))
      .filter((row) => row.count > 0)
      .sort((a, b) => b.count - a.count);

  return {
    checked: num(raw.checked) ?? 0,
    flagged: num(raw.flagged) ?? 0,
    byKind: counts(raw.by_kind, "kind") as { kind: string; count: number }[],
    bySource: counts(raw.by_source, "source") as { source: string; count: number }[],
    escalated: num(raw.escalated) ?? 0,
    judgeFailures: num(raw.judge_failures) ?? 0,
    // Отсутствие поля и ноль — разные факты, и сводить их нельзя: первое
    // означает «отчёт старше механизма», второе — «переспрашивать было нечего».
    requestioned: "requestioned" in raw ? (num(raw.requestioned) ?? 0) : null,
  };
}

/** Подписи разрезов состава аудитории. Порядок — порядок показа. */
const AUDIENCE_LABELS: Record<string, string> = {
  gender: "Пол",
  age_group: "Возраст",
  geo: "Тип населённого пункта",
  city: "Город",
};

const SURVEY_INDEX_KEYS: SurveyIndexKey[] = ["satisfaction", "perception", "nps"];

/** Словарь `{ключ: число}` → список пар в порядке писателя. */
function pairs(value: unknown): { id: string; share: number }[] | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return Object.entries(value as Record<string, unknown>).flatMap(([id, share]) => {
    const parsed = num(share);
    return parsed === null ? [] : [{ id, share: parsed }];
  });
}

/**
 * Показатель по одному охвату.
 *
 * Чего здесь НЕТ: подстановки нулей. Писатель у подавленного среза заменяет
 * числа на `null` и оставляет `n` с `base` — это его способ сказать «срез
 * слишком мал». Превратить такой `null` в ноль значило бы стереть единственное
 * различие между «посчитали, вышло ноль» и «считать не стали».
 */
function surveyStats(value: unknown): SurveyStats {
  const s = obj(value);
  const counts = obj(s.counts);
  const shares = pairs(s.shares);
  const rawRows = s.rows;

  return {
    n: num(s.n) ?? 0,
    base: num(s.base),
    belowThreshold: s.below_threshold === true,
    mean: num(s.mean),
    topBox: num(s.top_box),
    groups: pairs(s.groups),
    options: shares
      ? shares.map(({ id, share }) => ({ id, share, count: num(counts[id]) }))
      : null,
    errors: num(s.errors),
    texts: Array.isArray(s.texts) ? strings(s.texts) : null,
    rows:
      typeof rawRows === "object" && rawRows !== null && !Array.isArray(rawRows)
        ? Object.entries(rawRows as Record<string, unknown>).map(([id, row]) => ({
            id,
            themeId: str(obj(row).themeId),
            stats: surveyStats(row),
          }))
        : null,
  };
}

/**
 * Посчитанная анкета из агрегата.
 *
 * `null` при отсутствии поля: секции тогда нет вовсе. Пустая секция «Ответы на
 * анкету» сообщала бы, что анкету задавали и никто не ответил.
 */
function surveyOf(value: unknown): SurveyView | null {
  const raw = obj(value);
  if (Object.keys(raw).length === 0) return null;

  const questions: SurveyQuestionView[] = Object.entries(obj(raw.questions)).map(
    ([id, rawQuestion]) => {
      const q = obj(rawQuestion);
      return {
        id,
        number: num(q.number),
        type: str(q.type) ?? "open",
        block: str(q.block),
        label: str(q.label) ?? id,
        total: surveyStats(q.total),
        target: surveyStats(q.target),
      };
    },
  );
  // По номеру, а не по порядку ключей: порядок словаря переживает Mongo, но
  // держаться за него незачем — номер вопроса и есть порядок анкеты. Вопросы
  // без номера (их добавил оператор) идут после пронумерованных.
  questions.sort((a, b) => (a.number ?? Infinity) - (b.number ?? Infinity));

  const rawAudience = obj(raw.audience);
  const breakdowns = Object.entries(AUDIENCE_LABELS).flatMap(([key, label]) => {
    const counts = Object.entries(obj(rawAudience[key])).map(([value, personas]) => ({
      value,
      personas: num(personas) ?? 0,
    }));
    return counts.length ? [{ key, label, counts }] : [];
  });

  const rawIndices = obj(raw.indices);
  const indices = Object.fromEntries(
    SURVEY_INDEX_KEYS.map((key) => {
      const pair = obj(rawIndices[key]);
      return [key, { total: num(pair.total), target: num(pair.target) }];
    }),
  ) as SurveyView["indices"];

  return {
    questions,
    indices,
    audience: {
      total: num(rawAudience.total) ?? 0,
      target: num(rawAudience.target) ?? 0,
      targetRange: str(rawAudience.target_range),
      breakdowns,
    },
    minSegment: num(raw.min_segment) ?? 0,
    excludedByQa: num(raw.excluded_by_qa) ?? 0,
  };
}

function quotesOf(value: unknown): Quote[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((raw) => {
    const q = obj(raw);
    const text = str(q.text) ?? str(q.quote);
    if (!text) return [];
    return [{
      text,
      persona: str(q.persona) ?? str(q.persona_id) ?? "персона не указана",
      timecode: str(q.timecode),
    }];
  });
}

export function parseReport(raw: Record<string, unknown>): ReportView {
  const agg = obj(raw.aggregate);
  const breakdown = agg.segment_breakdown;
  const hasSegments = typeof breakdown === "object" && breakdown !== null;
  const bd = obj(breakdown);

  const segments: SegmentDimension[] = [];
  for (const [key, label] of Object.entries(SEGMENT_LABELS)) {
    const groups = obj(bd[key]);
    const rows = Object.entries(groups).map(([value, metrics]) => {
      const m = obj(metrics);
      return {
        value,
        overall: num(obj(m.core_scores_mean).overall_impression),
        nps: num(m.nps),
        retentionRate: num(m.retention_rate),
        personas: num(m.personas) ?? 0,
      };
    });
    if (rows.length) segments.push({ key, label, rows });
  }

  // Границы приходят посчитанными: сводить персональные разбросы к критерию —
  // арифметика, а её считает воркер (`_replication_bounds`). Повторить её здесь
  // значило бы завести вторую формулу, которая разойдётся с первой молча.
  const rawBounds = obj(agg.replication_bounds);
  const spread: ReportView["spread"] = {};
  for (const c of CRITERIA) {
    const b = obj(rawBounds[c]);
    const mean = num(b.mean);
    const min = num(b.min);
    const max = num(b.max);
    const stdev = num(b.stdev);
    if (mean !== null && min !== null && max !== null && stdev !== null) {
      spread[c] = { mean, min, max, stdev };
    }
  }

  return {
    scores: scoresOf(obj(agg.core_scores_mean)),
    spread,
    nps: num(agg.nps),
    retentionRate: num(agg.retention_rate),
    watchedShare: num(agg.watched_share_mean),
    emotionalIndex: num(agg.emotional_index),
    rationales: Object.fromEntries(
      Object.entries(obj(raw.rationales)).flatMap(([k, v]) =>
        typeof v === "string" && v.trim() ? [[k, v.trim()]] : [],
      ),
    ),
    topEmotions: (Array.isArray(agg.top_emotions) ? agg.top_emotions : []).flatMap((raw) => {
      const e = obj(raw);
      const name = str(e.name) ?? str(e.emotion);
      const pct = num(e.pct) ?? num(e.share);
      return name && pct !== null ? [{ name, pct }] : [];
    }),
    sampleSize: num(agg.sample_size) ?? 0,
    excludedByQa: num(agg.excluded_by_qa) ?? 0,
    replicationCount: num(agg.replication_count) ?? 1,
    replicationStability: num(agg.replication_stability),
    narrative: strings(raw.narrative),
    themes: (Array.isArray(raw.themes) ? raw.themes : []).flatMap((rawTheme) => {
      const t = obj(rawTheme);
      const title = str(t.title);
      if (!title) return [];
      return [{
        title,
        agreement: str(t.agreement) ?? "не определено",
        summary: str(t.summary) ?? "",
        quotes: quotesOf(t.quotes),
      }];
    }),
    strengths: strings(raw.strengths),
    weaknesses: strings(raw.weaknesses),
    recommendation: num(agg.recommendation_mean),
    qa: qaOf(raw.qa_summary),
    modelsUsed: (() => {
      const m = obj(raw.models_used);
      const text = str(m.text);
      const vision = str(m.vision);
      const judge = str(m.judge);
      if (!text && !vision && !judge) return null;
      return { text: text ?? "—", vision: vision ?? "—", judge: judge ?? "—" };
    })(),
    asked: (Array.isArray(raw.survey_asked) ? raw.survey_asked : []).flatMap((rawQ) => {
      const q = obj(rawQ);
      const label = str(q.label);
      if (!label) return [];
      const baseKey = str(q.baseKey);
      return [{
        id: str(q.id) ?? "?",
        label,
        type: str(q.type) ?? "открытый",
        ...(baseKey && (CRITERIA as readonly string[]).includes(baseKey)
          ? { baseKey: baseKey as Criterion }
          : {}),
      }];
    }),
    riskPoints: (Array.isArray(raw.retention_risk_points) ? raw.retention_risk_points : [])
      .flatMap((rawPoint) => {
        const p = obj(rawPoint);
        const timecode = str(p.timecode);
        if (!timecode) return [];
        return [{
          timecode,
          note: str(p.scene) ?? str(p.note) ?? "",
          personas: num(p.personas) ?? 0,
        }];
      }),
    segments,
    suppressedSegments: (Array.isArray(bd.suppressed) ? bd.suppressed : []).flatMap((rawSeg) => {
      const s = obj(rawSeg);
      const value = str(s.value);
      const dimension = str(s.dimension);
      return value && dimension
        ? [{ dimension, value, personas: num(s.personas) ?? 0 }]
        : [];
    }),
    minSegmentPersonas: num(bd.min_personas) ?? 0,
    hasSegments,
    disclaimer: str(raw.disclaimer),
    degraded: strings(raw.degraded),
    survey: surveyOf(agg.survey),
  };
}

export function segmentLabel(segment: Record<string, string>): string | null {
  const parts = Object.keys(SEGMENT_LABELS)
    .map((k) => segment[k])
    .filter((v): v is string => Boolean(v));
  return parts.length ? parts.join(" · ") : null;
}

export function parseAnswer(card: {
  personaId: string;
  personaName: string | null;
  replication: number;
  segment: Record<string, string>;
  answer: Record<string, unknown>;
  qaFlags: Record<string, unknown>[];
}): AnswerView {
  const body = card.answer;
  const perception = obj(body.perception);
  const verbatims = obj(body.verbatims);
  const scores = scoresOf(obj(body.scores));
  const name = card.personaName ?? card.personaId;

  return {
    personaId: card.personaId,
    personaName: name,
    initials: initials(name),
    avatarHue: avatarHue(card.personaId),
    replication: card.replication,
    segmentLabel: segmentLabel(card.segment),
    scores,
    overall: scores.overall_impression,
    retentionIntent: str(perception.retention_intent),
    watchedShare: num(perception.watched_share_pct),
    nps: num(perception.recommendation_nps_1_to_10),
    emotions: strings(perception.emotions_evoked),
    // Первое непустое обоснование: у анкеты их несколько, а в свёрнутой строке
    // место под одно. Показывать «почему такое впечатление» — то, ради чего
    // строку и разворачивают.
    verbatim: str(verbatims.why_impression)
      ?? Object.values(verbatims).map(str).find((v): v is string => Boolean(v))
      ?? null,
    groundingRefs: strings(body.grounding_refs).flatMap((ref) => {
      const m = REF.exec(ref);
      return m ? [{ timecode: m[1], note: m[2] }] : [];
    }),
    // `reasons` — СПИСОК, и он единственный источник слов. `verdict` сюда не
    // подставляется ни при каких условиях: у всех забракованных ответов он
    // равен «regenerate», то есть сообщает решение системы вместо причины.
    // Именно этот запасной путь прятал промах по имени поля: без него значок
    // был бы пустым, а пустоту заметили бы в первый день.
    qaFlags: card.qaFlags.map((f) => ({
      kind: str(f.kind) ?? "проверка",
      confidence: num(f.confidence),
      reasons: strings(f.reasons),
      source: str(f.source) ?? "rule",
    })),
    surveyAnswers: flatten(obj(body.survey_answers)),
    verbatims: flatten(verbatims),
  };
}

/**
 * Строка вопроса в том виде, в каком её печатает промпт респондента:
 * `[q-77] (scale) как дела?`. Модель охотно берёт её ключом ответа целиком.
 */
const PROMPT_LINE = /^\[([^\]]+)\]\s*(?:\(([^)]*)\)\s*)?(.*)$/;

/** Ключ ответа во всех видах, какими персона могла назвать вопрос. */
function answerKeys(answers: Record<string, string>): Map<string, string> {
  const out = new Map<string, string>();
  for (const [raw, value] of Object.entries(answers)) {
    const key = raw.trim();
    const put = (k: string) => {
      const norm = k.trim().toLocaleLowerCase();
      if (norm && !out.has(norm)) out.set(norm, value);
    };
    put(key);
    const m = PROMPT_LINE.exec(key);
    if (m) {
      put(m[1]);
      put(m[3]);
    }
  }
  return out;
}

const TYPED_IN_PERCEPTION: Record<string, "watchedShare" | "retentionIntent" | "recommendation"> = {
  watched_share: "watchedShare",
  retention: "retentionIntent",
  nps: "recommendation",
};

/**
 * Ответ персоны на заданный вопрос — откуда бы он ни пришёл. `null` — не ответила.
 *
 * Три источника, потому что промпт кладёт ответы в три разных места: базовые
 * баллы в `scores`, типовые вопросы в `perception`, остальное в
 * `survey_answers` — и там ключом может оказаться идентификатор, формулировка
 * ЛИБО целая строка промпта «[q-77] (scale) как дела?».
 *
 * Живёт здесь, а не в карточке, ровно потому, что это уже четвёртый случай
 * одной семьи: тот же разрыв чинили в `qa/checks.py` дважды и в
 * `content/pack.py` один раз. Место, где он проверяется тестом, должно быть
 * одно.
 */
export function answerForQuestion(a: AnswerView, q: AskedQuestion): string | null {
  if (q.baseKey) {
    const score = a.scores?.[q.baseKey];
    if (typeof score === "number") return `${score} из 10`;
  }

  const keys = answerKeys(a.surveyAnswers ?? {});
  const direct = keys.get(q.id.trim().toLocaleLowerCase())
    ?? keys.get(q.label.trim().toLocaleLowerCase());
  if (direct) return direct;

  switch (TYPED_IN_PERCEPTION[q.type]) {
    case "watchedShare":
      return a.watchedShare !== null && a.watchedShare !== undefined
        ? `${a.watchedShare}%` : null;
    case "retentionIntent":
      return a.retentionIntent || null;
    case "recommendation":
      return a.nps !== null && a.nps !== undefined ? `${a.nps} из 10` : null;
    default:
      return null;
  }
}


/**
 * Короткая подпись категории досмотра для узкой колонки.
 *
 * ─── Зачем ────────────────────────────────────────────────────────────────
 * Полная формулировка корпуса — «Скорее хотелось досмотреть до конца» — в
 * колонку строки персоны не влезает и обрезается многоточием на середине
 * слова. Три коротких подписи различимы с одного взгляда, а полная
 * формулировка остаётся в раскрытой части.
 *
 * ─── Почему неизвестное показывается как есть ─────────────────────────────
 * Прочерк вместо непонятой строки означал бы, что расхождение промпта с
 * моделью заметит только тот, кто полезет в JSON. Приведение к словарю корпуса
 * делает воркер (agent_core/schemas/answer.py); если оно не сработало, это
 * должно быть видно на экране.
 */
const RETENTION_SHORT: Record<string, string> = {
  "Скорее хотелось досмотреть до конца": "Досмотрит",
  "Скорее хотелось остановить просмотр": "Выключит",
  "Затрудняюсь ответить": "Не решил",
};

export function retentionShort(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  if (!text) return "—";
  return RETENTION_SHORT[text] ?? text;
}
