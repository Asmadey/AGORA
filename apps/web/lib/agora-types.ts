/**
 * Типы предметной области AGORA.
 *
 * ВРЕМЕННО живут здесь. По Decision Log #4 источник истины — canonical JSON Schema
 * в packages/shared/schemas, из неё генерируются и TS-типы, и Pydantic-модели
 * (задача #4). До неё эти типы — рабочая формулировка контракта, а не финальная.
 */

// ─── Persona DNA: 8 категорий (PRD §9) ────────────────────────────────────

export type BigFiveScore = 1 | 2 | 3 | 4 | 5;

export interface BigFive {
  openness: BigFiveScore;
  conscientiousness: BigFiveScore;
  extraversion: BigFiveScore;
  agreeableness: BigFiveScore;
  neuroticism: BigFiveScore;
}

export type AgeGroup = "14-17" | "18-24" | "25-34" | "35-44" | "45-59" | "60+";
export type Geo = "столицы" | "центры субъектов" | "иные НП";
export type Gender = "муж" | "жен";

export interface Demographics {
  gender: Gender;
  age: number;
  ageGroup: AgeGroup;
  geo: Geo;
  city: string;
  education: string;
  occupation: string;
  income: string;
  children: string;
  maritalStatus: string;
}

export interface ValuesBeliefs {
  coreValues: string[];
  socialPriorities: string[];
  culturalOutlook: string;
  philosophy: string;
  attitudeToFuture: string;
}

/** Категория 4 — то, ради чего всё затевалось: как человек смотрит видео. */
export interface ViewingBehaviour {
  favouriteGenres: string[];
  avoidedGenres: string[];
  violenceTolerance: string;
  paceTolerance: string;
  lengthTolerance: string;
  franchiseLoyalty: string;
  actorLoyalty: string;
  recommendationInfluence: string;
  reactionToIdeology: string;
  reactionToAdvertising: string;
  productionExpectations: string;
  attentionSpan: string;
}

export interface CommunicationStyle {
  tone: string;
  vocabulary: string;
  verbosity: string;
  humour: string;
  criticismStyle: string;
}

export interface DecisionMaking {
  riskAppetite: string;
  deliberation: string;
  peerInfluence: string;
  trustInAuthority: string;
  priceSensitivity: string;
}

export interface TechnologyUse {
  devices: string[];
  platforms: string[];
  viewingContext: string;
  secondScreen: string;
}

export interface Lifestyle {
  hobbies: string[];
  dailyRhythm: string;
  socialLife: string;
  mediaDiet: string[];
  careerPath: string;
}

export interface PersonaDNA {
  demographics: Demographics;
  bigFive: BigFive;
  values: ValuesBeliefs;
  viewing: ViewingBehaviour;
  communication: CommunicationStyle;
  decisions: DecisionMaking;
  technology: TechnologyUse;
  lifestyle: Lifestyle;
}

export interface Persona {
  id: string;
  name: string;
  /** Поколение считается из возраста, но хранится явно — так его видно в списке. */
  generation: string;
  jobTitle: string;
  location: string;
  avatarHue: number;
  createdAt: string;
  personaSetId: string;
  dna: PersonaDNA;
  narrative: string;
  seed: number;
}

// ─── Прогоны и отчёты ─────────────────────────────────────────────────────

export const CRITERIA = [
  "overall_impression",
  "plot",
  "acting",
  "music",
  "cinematography",
] as const;

export type Criterion = (typeof CRITERIA)[number];

export const CRITERIA_LABELS: Record<Criterion, string> = {
  overall_impression: "Общее впечатление",
  plot: "Сюжет",
  acting: "Актёрская игра",
  music: "Музыка",
  cinematography: "Операторская работа",
};

export type Scores = Record<Criterion, number>;

/** Разброс по повторам. Заполняется только при replicationCount > 1. */
export interface Confidence {
  mean: number;
  min: number;
  max: number;
  stdev: number;
}

export interface PersonaAnswer {
  personaId: string;
  scores: Scores;
  confidence?: Partial<Record<Criterion, Confidence>>;
  wouldRecommend: boolean;
  watchedUntil: number;
  emotions: string[];
  verbatim: string;
  /** Каждое суждение обязано опираться на таймкод — иначе это догадка. */
  groundingRefs: { timecode: string; note: string }[];
  qaFlags: string[];
}

export interface AggregateReport {
  scores: Scores;
  confidence?: Partial<Record<Criterion, Confidence>>;
  nps: number;
  retentionRate: number;
  emotionalIndex: number;
  topEmotions: { name: string; pct: number }[];
  segments: { segment: string; scores: Scores; note: string }[];
}

export interface GroupSynthesis {
  themes: { title: string; agreement: "согласие" | "несогласие" | "раскол"; summary: string; quotes: { persona: string; text: string; timecode?: string }[] }[];
  strengths: string[];
  weaknesses: string[];
}

export type TaskStatus = "QUEUED" | "RUNNING" | "REPORT_READY" | "FAILED";

export interface PipelineNode {
  key: string;
  label: string;
  status: "pending" | "running" | "done" | "failed";
  detail?: string;
}

export interface StudyRun {
  id: string;
  projectName: string;
  contentTitle: string;
  mode: "short" | "long";
  durationSec: number;
  audienceSize: number;
  replicationCount: number;
  status: TaskStatus;
  createdAt: string;
  parentTaskId?: string;
  aggregate?: AggregateReport;
  synthesis?: GroupSynthesis;
  answers?: PersonaAnswer[];
  narrative?: string[];
}

// ─── Анкета: конструктор вопросов (задача #10) ────────────────────────────

/**
 * Типы вопросов P1-конструктора (PRD §строка 60, acceptance задачи #10).
 * Список закрытый: воркер умеет разбирать ответ только этих форм, и валидатор
 * анкеты отвергает всё остальное. Добавление типа — это изменение схемы ответа
 * персоны, а не правка интерфейса: вместе с ним правятся `prompts/respondent.user.md`,
 * миграция засева и разбор в `agent_core`.
 */
export type QuestionType =
  | "scale"
  | "single_choice"
  | "multi_choice"
  | "matrix_single"
  | "open";

/**
 * Ключи пяти базовых критериев. Именно по ним посчитаны средние в корпусе
 * 165 респондентов, поэтому ключ — часть контракта с данными, а не подпись
 * на экране. Подпись менять можно, ключ — нет.
 */
export type BaseCriterionKey =
  | "overall_impression"
  | "plot"
  | "acting"
  | "music"
  | "cinematography";

/** Вариант ответа закрытого вопроса. */
export interface SurveyOption {
  /**
   * Уникален внутри вопроса. Ответ персоны адресует вариант ИМЕННО им:
   * подпись правят, идентификатор — нет.
   */
  id: string;
  label: string;
  /**
   * Служебный вариант вроде «Затрудняюсь ответить». В долях по содержательным
   * вариантам не участвует, но остаётся в знаменателе — доли считаются
   * «в % от опрошенных», как подписано у заказчика.
   */
  service?: boolean;
}

/** Строка матрицы. Ответ даётся по каждой строке, а не по вопросу. */
export interface SurveyRow {
  id: string;
  label: string;
  /** Тема, к которой относится строка: единица выбора оператора. */
  themeId?: string;
}

/** Тема матрицы. Галочка ставится на теме, строки идут целиком. */
export interface SurveyTheme {
  id: string;
  label: string;
}

export interface SurveyQuestion {
  id: string;
  /** Задан только у пяти базовых критериев; у пользовательских вопросов — undefined. */
  baseKey?: BaseCriterionKey;
  label: string;
  type: QuestionType;
  /**
   * Границы шкалы. Обязательны и осмысленны только при type === "scale";
   * у выбора из списка шкалы нет и быть не может.
   */
  scaleMin?: number;
  scaleMax?: number;
  /** Подсказка для персоны — что именно оценивать. Необязательна. */
  hint?: string;
  /** Номер вопроса в анкете заказчика — им его называют отчёт и выгрузка. */
  number?: number;
  /** Блок верхнего уровня: верхняя строка двухуровневой шапки выгрузки. */
  block?: string;
  /** Варианты закрытого вопроса. Без них закрытый вопрос становится открытым. */
  options?: SurveyOption[];
  /** Потолок выбора при type === "multi_choice". */
  maxChoices?: number;
  /** Варианты, выбираемые только в одиночку. */
  exclusiveOptionIds?: string[];
  /** Строки матрицы при type === "matrix_single". */
  rows?: SurveyRow[];
  /** Темы матрицы. */
  themes?: SurveyTheme[];
  /** Вопрос, выбор тем в котором определяет состав строк этого. */
  dependsOnQuestion?: string;
  /** Единица выбора оператора у матрицы. */
  selectableBy?: "theme";
}
