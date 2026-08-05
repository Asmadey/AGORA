/**
 * Client-side AI wrapper for AGORA.
 *
 * IMPORTANT: this module contains NO API keys and makes NO direct LLM calls.
 * Every function posts to a server route handler under /api/*, where the real
 * LLM logic runs (see lib/ai-server.ts). Function signatures are unchanged so
 * existing UI components keep working.
 */
import type { Agent, SurveyResponse, Report } from './types';

export type { Agent, SurveyResponse, Report } from './types';

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `Request to ${url} failed (${res.status})`;
    try {
      const data = await res.json();
      if (data?.error) msg = data.error;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export async function fetchNewsContext(): Promise<any> {
  const { context } = await postJson<{ context: any }>('/api/news-context', {});
  return context;
}

/**
 * Генерация аудитории через заземлённый на корпус генератор.
 *
 * Контракт тела задаёт parseAudienceChoice (lib/audience.ts): поля читаются с
 * верхнего уровня, ветка «переиспользовать набор» отличается наличием
 * personaSetId. Прежняя версия слала {size, context, options} — вокабуляр
 * прототипа, которого маршрут не понимает, и отвечал он на это 400 на каждую
 * попытку. Дефект был невидим: страница /audience — единственный её вызывающий,
 * а CDD #9 прогоняет генератор напрямую, минуя и маршрут, и страницу.
 *
 * `context` из сигнатуры убран намеренно. Раньше сюда подмешивался новостной
 * контекст — источник, которого нет в корпусе. Он влиял на персон, а метрика
 * persona_grounding о нём не знала: заземление считалось по корпусу, а текст
 * персоны частично приезжал извне.
 */
export async function generateAudience(
  criteria: {
    size: number;
    ageGroups: string[];
    geos: string[];
    genders: string[];
    education?: string[];
  },
): Promise<{ personaSetId: string; size: number; personas: unknown[] }> {
  return await postJson<{ personaSetId: string; size: number; personas: unknown[] }>(
    '/api/audience',
    criteria,
  );
}

export async function simulateSurvey(
  agents: Agent[],
  project: any,
  survey: any
): Promise<any[]> {
  const { responses } = await postJson<{ responses: any[] }>('/api/simulate', {
    agents,
    project,
    survey,
  });
  return responses;
}

export async function generateReport(responses: any[], survey: any): Promise<any> {
  const { report } = await postJson<{ report: any }>('/api/report', {
    responses,
    survey,
  });
  return report;
}

export async function chatWithAudience(
  message: string,
  history: { role: 'user' | 'assistant'; content: string }[],
  agents: Agent[],
  responses: any[],
  selectedAgentId: string | 'all',
  projectContext: any = { title: 'Константинополь', description: 'историческая драма' }
): Promise<string> {
  const { response } = await postJson<{ response: string }>('/api/chat', {
    message,
    history,
    agents,
    responses,
    selectedAgentId,
    projectContext,
  });
  return response;
}

export async function generateNewsAnalysis(
  agents: Agent[],
  realNews: Array<{ title: string; source: string; summary: string }>
): Promise<any> {
  return await postJson<any>('/api/news-analysis', { agents, realNews });
}
