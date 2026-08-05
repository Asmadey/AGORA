/**
 * Server-side AI core for AGORA.
 *
 * All LLM calls live here and run ONLY on the server. API keys are read from
 * environment variables and never reach the browser. Route handlers under
 * app/api/* import this module; the client (lib/ai.ts) talks to those routes.
 *
 * Text path : OpenAI-compatible provider (configurable, defaults to timeweb).
 * Video path: Google Gemini native multimodal (Files API), ported from the
 *             original `agora` Express backend.
 */
import OpenAI from 'openai';
import { GoogleGenAI, Type } from '@google/genai';
import type { Agent } from './types';

// ---------- provider config (env only) ----------

const OPENAI_BASE_URL = process.env.OPENAI_BASE_URL || 'https://api.timeweb.ai/v1';
const AI_MODEL = process.env.AI_MODEL || 'gemini/gemini-3-flash-preview';
const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-3-flash-preview';

function getOpenAI(): OpenAI {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error(
      'OPENAI_API_KEY is not set. Configure it in your environment (.env.local).'
    );
  }
  return new OpenAI({ apiKey, baseURL: OPENAI_BASE_URL });
}

function getGemini(): GoogleGenAI {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error(
      'GEMINI_API_KEY is not set. Required for native video analysis.'
    );
  }
  return new GoogleGenAI({ apiKey });
}

function extractJson(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    const match =
      text.match(/```json\s*([\s\S]*?)\s*```/) || text.match(/\{[\s\S]*\}/);
    if (match) {
      try {
        return JSON.parse(match[1] || match[0]);
      } catch {
        /* fall through */
      }
    }
    throw new Error('Failed to extract JSON from AI response.');
  }
}

async function chatJson(prompt: string): Promise<any> {
  const openai = getOpenAI();
  const response = await openai.chat.completions.create({
    model: AI_MODEL,
    messages: [{ role: 'user', content: prompt }],
    response_format: { type: 'json_object' },
  });
  return extractJson(response.choices[0].message.content || '{}');
}

// ---------- audience / personas ----------

export async function simulateSurvey(
  agents: Agent[],
  project: any,
  survey: any
): Promise<any[]> {
  const episodesContext =
    project.episodes && project.episodes.length > 0
      ? project.episodes
          .map((ep: any, i: number) => {
            let text = `${i + 1}. ${ep.title} (${ep.url})`;
            if (ep.metadata) {
              text += `\n  - Реальное название видео: ${ep.metadata.title}\n  - Канал/Автор: ${ep.metadata.author_name}\n  - Платформа: ${ep.metadata.provider}`;
            }
            return text;
          })
          .join('\n')
      : 'Нет данных о видео.';

  const prompt = `
    Ты - система симуляции фокус-группы "Агора".
    Ниже представлен список из ${agents.length} агентов (синтетических личностей).
    Они только что посмотрели проект "${project.title}" (${project.description}).

    Материалы (эпизоды/видео), которые они посмотрели:
    ${episodesContext}

    Для КАЖДОГО агента сгенерируй ответы на анкету.
    Ответы должны строго соответствовать профилю агента (его возрасту, ценностям, характеру, новостной памяти и экономическому контексту), а также опираться на детали просмотренного контента.

    Вопросы анкеты:
    ${JSON.stringify(survey.questions, null, 2)}

    Для каждого агента верни объект со следующими полями:
    - agentId: id агента
    - answers: объект, где ключи - это ID вопросов из анкеты, а значения - ответы агента.
      - Для типа 'rating' или 'nps': число от 1 до scale.
      - Для типа 'emotions' или 'values': массив строк (до max элементов).
      - Для типа 'open': строка (развернутый комментарий 2-3 предложения).
      - Для типа 'matrix' или 'slogan': строка (выбранный вариант из options).
      - Для типа 'retention': булево значение (true - досмотрел бы, false - выключил бы).

    Верни ТОЛЬКО валидный JSON объект с ключом "responses", содержащим массив этих объектов.

    Агенты:
    ${JSON.stringify(agents, null, 2)}
  `;

  const parsed = await chatJson(prompt);
  return parsed.responses || [];
}

// ---------- report ----------

export async function generateReport(responses: any[], survey: any): Promise<any> {
  const prompt = `
    Проанализируй результаты опроса синтетической аудитории.

    Анкета:
    ${JSON.stringify(survey, null, 2)}

    Ответы:
    ${JSON.stringify(responses, null, 2)}

    Верни валидный JSON объект со следующей структурой:
    - summary: Развернутое текстовое аналитическое резюме (3-4 абзаца). Опиши общие впечатления, выдели сегменты аудитории, укажи сильные и слабые стороны на основе данных.
    - npsScore: Индекс NPS (число от -100 до 100), если в анкете был вопрос типа 'nps'.
    - topEmotions: массив { name: string, count: number } (если был вопрос 'emotions').
    - topValues: массив { name: string, count: number } (если был вопрос 'values').
    - averageRatings: объект, где ключи - ID вопросов типа 'rating', значения - средний балл.
    - retentionRate: процент удержания (0-100), если был вопрос 'retention'.
    - insights: массив из 3-5 ключевых инсайтов (строки).
  `;
  return await chatJson(prompt);
}

// ---------- focus-group chat ----------

export async function chatWithAudience(
  message: string,
  history: { role: 'user' | 'assistant'; content: string }[],
  agents: Agent[],
  responses: any[],
  selectedAgentId: string | 'all',
  projectContext: any = { title: 'Константинополь', description: 'историческая драма' }
): Promise<string> {
  const episodesContext =
    projectContext.episodes && projectContext.episodes.length > 0
      ? projectContext.episodes
          .map((ep: any, i: number) => {
            let text = `${i + 1}. ${ep.title} (${ep.url})`;
            if (ep.metadata) {
              text += `\n  - Реальное название видео: ${ep.metadata.title}\n  - Канал/Автор: ${ep.metadata.author_name}\n  - Платформа: ${ep.metadata.provider}`;
            }
            return text;
          })
          .join('\n')
      : 'Нет данных о видео.';

  const memoryInstruction = `ОЧЕНЬ ВАЖНО: У тебя ИДЕАЛЬНАЯ память на все просмотренные эпизоды/материалы проекта "${projectContext.title}". Ты помнишь каждую секунду видео, реплики персонажей, как они выглядят, как они себя ведут, что происходит на фоне и на какой конкретной минуте или секунде это было. Если пользователь спрашивает детали видео (таймкоды, визуальное описание сцен, кто что сказал), уверенно и детально отвечай на эти вопросы, опираясь на название и суть видео, а также на ответы анкеты. Если точного видео нет, домысли реалистичные детали, подходящие проекту "${projectContext.title}" (${projectContext.description}).`;

  let systemPrompt = '';
  if (selectedAgentId === 'all') {
    systemPrompt = `
      Ты - симулятор фокус-группы "Агора". Пользователь задает вопрос всей аудитории (${agents.length} человек), которая только что посмотрела проект "${projectContext.title}" (${projectContext.description}).

      Просмотренные видео-материалы:
      ${episodesContext}

      ${memoryInstruction}

      Твоя задача - сгенерировать ответ в формате живого обсуждения, где несколько разных агентов (2-4 человека) высказывают свои мнения, вспоминают конкретные сцены из видео, спорят или соглашаются друг с другом.
      Их ответы должны строго базироваться на их профилях, ответах в анкете и деталях просмотренного видео.

      Профили агентов: ${JSON.stringify(agents)}
      Их ответы в анкете: ${JSON.stringify(responses)}

      Формат ответа:
      [Имя агента, Возраст, Профессия]: "Текст реплики (включая детали видео, таймкоды, эмоции)"
      [Имя другого агента]: "Текст реплики"
    `;
  } else {
    const agent = agents.find((a) => a.id === selectedAgentId);
    const response = responses.find((r) => r.agentId === selectedAgentId);
    systemPrompt = `
      Ты - синтетический респондент фокус-группы "Агора". Ты только что посмотрел проект "${projectContext.title}" (${projectContext.description}).

      Просмотренные видео-материалы:
      ${episodesContext}

      ${memoryInstruction}

      Твой профиль: ${JSON.stringify(agent)}
      Твои ответы на анкету по проекту: ${JSON.stringify(response)}

      Отвечай на вопросы пользователя строго от своего лица, сохраняя свой характер, возраст, профессию, убеждения и память о своих ответах в анкете. В диалоге упоминай конкретные моменты из видео, чтобы доказать, что ты его внимательно смотрел.
    `;
  }

  const openai = getOpenAI();
  const apiResponse = await openai.chat.completions.create({
    model: AI_MODEL,
    messages: [
      { role: 'system', content: systemPrompt },
      ...history,
      { role: 'user', content: message },
    ],
  });
  return apiResponse.choices[0].message.content || '';
}

// ---------- news analysis ----------

