import { readFile } from "node:fs/promises";
import path from "node:path";

/**
 * Реестр промптов (задача #26) — чтение seed-версий с диска.
 *
 * ЭТАП 1 из 2. Источником истины должна стать таблица prompts с версиями,
 * is_active и is_default (acceptance задачи #26), но сами тексты уже существуют
 * в prompts/*.md, и это настоящие файлы, а не макет. Поэтому просмотр промпта
 * работает сегодня и показывает то, что реально уйдёт в модель.
 *
 * Чего здесь ещё нет и не может быть до БД: редактирование, версии, переключение
 * активной версии, restore default, dry-run. Всё это операции над строками
 * таблицы, а не над файлами: править seed-файлы из интерфейса означало бы
 * менять дефолт для всех арендаторов сразу и терять возможность откатиться.
 */

export interface PromptMeta {
  key: string;
  stage: string;
  desc: string;
}

/** 13 seed-промптов. Порядок внутри стадии — порядок вызова в пайплайне. */
export const PROMPT_REGISTRY: PromptMeta[] = [
  { key: "persona.generate", stage: "Персоны", desc: "Генерация персоны из сегмента корпуса" },
  { key: "portrait.distill", stage: "Персоны", desc: "Дистилляция портрета аудитории из датасета" },
  { key: "dataset.unification", stage: "Знания", desc: "Сборка корпуса из анкет и стенограмм" },
  { key: "content.frame_analysis", stage: "Контент", desc: "Разбор панели кадров в JSON сцены" },
  { key: "content.stitch_summary", stage: "Контент", desc: "Склейка понимания видео по таймлайну" },
  { key: "respondent.system", stage: "Оценка", desc: "Системная роль персоны-респондента" },
  { key: "respondent.user", stage: "Оценка", desc: "Предъявление материала и анкеты" },
  { key: "qa.consistency", stage: "QA", desc: "Поиск противоречий в ответах" },
  { key: "qa.grounding", stage: "QA", desc: "Поиск выдуманных сцен и таймкодов" },
  { key: "qa.diversity", stage: "QA", desc: "Детект mode collapse в ответах" },
  { key: "analytics.report", stage: "Отчёт", desc: "Сборка агрегата и нарратива" },
  { key: "chat.analyst", stage: "Чат", desc: "Аналитик по результатам исследования" },
  { key: "chat.persona_followup", stage: "Чат", desc: "Допрос персоны после просмотра" },
];

export function findPrompt(key: string): PromptMeta | undefined {
  return PROMPT_REGISTRY.find((p) => p.key === key);
}

/**
 * Каталог prompts/ лежит в корне монорепо, а процесс Next.js стартует из apps/web.
 * В standalone-сборке рабочий каталог снова другой, поэтому путь ищется среди
 * кандидатов, а не задаётся одной константой: единственная захардкоженная строка
 * сломалась бы ровно при переходе на docker и молча — страница просто не нашла бы
 * файл.
 */
const CANDIDATE_ROOTS = [
  path.join(process.cwd(), "..", "..", "prompts"),
  path.join(process.cwd(), "prompts"),
  "/app/prompts",
];

export interface PromptSource {
  /** Заголовок и строка «Переменные: …» — всё до разделителя `---`. */
  header: string;
  /** Сам шаблон, который уходит в модель. */
  template: string;
  /** Имена {{плейсхолдеров}} в порядке первого появления. */
  variables: string[];
}

/** Извлекает {{имена}} без повторов. Именно они валидируются задачей #26. */
export function extractVariables(text: string): string[] {
  const found = text.matchAll(/\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g);
  return [...new Set([...found].map((m) => m[1]))];
}

export async function loadPromptSource(key: string): Promise<PromptSource | null> {
  if (!findPrompt(key)) return null;

  for (const root of CANDIDATE_ROOTS) {
    try {
      const raw = await readFile(path.join(root, `${key}.md`), "utf8");
      const sep = raw.indexOf("\n---\n");
      const header = sep === -1 ? "" : raw.slice(0, sep).trim();
      const template = sep === -1 ? raw.trim() : raw.slice(sep + 5).trim();
      return { header, template, variables: extractVariables(raw) };
    } catch {
      // следующий кандидат
    }
  }
  return null;
}

/** Счётчики переменных для списка. Читает все файлы разом — их тринадцать. */
export async function loadVariableCounts(): Promise<Record<string, number | null>> {
  const entries = await Promise.all(
    PROMPT_REGISTRY.map(async (p) => {
      const src = await loadPromptSource(p.key);
      return [p.key, src ? src.variables.length : null] as const;
    }),
  );
  return Object.fromEntries(entries);
}
