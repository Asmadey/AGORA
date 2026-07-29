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
 * Список закрытый: воркер умеет разбирать ответ только этих пяти форм, и
 * валидатор анкеты отвергает всё остальное. Добавление шестого типа — это
 * изменение схемы ответа персоны, а не правка интерфейса.
 */
export type QuestionType =
  | "scale"
  | "emotions"
  | "retention"
  | "recommendation"
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

export interface SurveyQuestion {
  id: string;
  /** Задан только у пяти базовых критериев; у пользовательских вопросов — undefined. */
  baseKey?: BaseCriterionKey;
  label: string;
  type: QuestionType;
  /** Границы шкалы. Осмысленны только при type === "scale". */
  scaleMin: number;
  scaleMax: number;
  /** Подсказка для персоны — что именно оценивать. Необязательна. */
  hint?: string;
}
