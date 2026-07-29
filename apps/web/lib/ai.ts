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

export async function generateAudience(
  size = 20,
  context?: any,
  options?: Record<string, any>
): Promise<Agent[]> {
  const { agents } = await postJson<{ agents: Agent[] }>('/api/audience', {
    size,
    context,
    options,
  });
  return agents;
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
