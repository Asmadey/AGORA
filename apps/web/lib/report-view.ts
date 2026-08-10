import { CRITERIA, type Criterion } from "./agora-types";

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
  disclaimer: string | null;
  degraded: string[];
}

export interface Quote {
  text: string;
  persona: string;
  timecode: string | null;
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
  qaFlags: string[];
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
    qaFlags: card.qaFlags.flatMap((f) => {
      const reason = str(f.reason) ?? str(f.verdict);
      return reason ? [reason] : [];
    }),
  };
}
