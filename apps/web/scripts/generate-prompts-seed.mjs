#!/usr/bin/env node
/**
 * Генератор миграции засева промптов (задача #26).
 *
 * Читает 13 файлов prompts/*.md, извлекает ключ (имя файла без .md), стадию
 * (из реестра), шаблон (содержимое файла) и переменные ({{плейсхолдеры}}),
 * после чего генерирует INSERT-операторы с ON CONFLICT DO NOTHING.
 *
 * Миграция идемпотентна: повторный прогон не плодит строки и не затирает
 * пользовательские версии. Дефолты сеются от имени владельца (tenant_id IS NULL),
 * а не из-под agora_app — политика prompts_write_own_only требует
 * tenant_id = current_tenant(), а у дефолта он NULL.
 *
 * Запуск:
 *   npm run prompts:seed:sql
 *
 * Вывод: infra/postgres/init/07_prompts_seed.sql
 */
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const PROMPTS_DIR = path.join(REPO_ROOT, "prompts");
const OUT_FILE = path.join(REPO_ROOT, "infra", "postgres", "init", "07_prompts_seed.sql");

/** Реестр: key → stage. Должен совпадать с apps/web/lib/prompt-registry.ts. */
const STAGE_MAP = {
  "persona.generate": "Персоны",
  "portrait.distill": "Персоны",
  "dataset.unification": "Знания",
  "content.frame_analysis": "Контент",
  "content.stitch_summary": "Контент",
  "respondent.system": "Оценка",
  "respondent.user": "Оценка",
  "qa.consistency": "QA",
  "qa.grounding": "QA",
  "qa.diversity": "QA",
  "analytics.report": "Отчёт",
  "chat.analyst": "Чат",
  "chat.persona_followup": "Чат",
};

/** Извлекает {{имена}} без повторов — та же логика, что в prompt-registry.ts. */
function extractVariables(text) {
  const found = text.matchAll(/\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g);
  return [...new Set([...found].map((m) => m[1]))];
}

/**
 * Экранирует строку для использования как SQL-строковый литерал в одинарных
 * кавычках. Удваивает одинарные кавычки и обратные слеши.
 */
function sqlEscape(str) {
  return str.replace(/\\/g, "\\\\").replace(/'/g, "''");
}

/** Экранирует значение для SQL jsonb-литерала (строка в одинарных кавычках). */
function sqlJsonEscape(obj) {
  return sqlEscape(JSON.stringify(obj));
}

async function main() {
  const keys = Object.keys(STAGE_MAP).sort();
  const inserts = [];

  for (const key of keys) {
    const filePath = path.join(PROMPTS_DIR, `${key}.md`);
    let raw;
    try {
      raw = await readFile(filePath, "utf8");
    } catch {
      console.error(`Файл не найден: ${filePath}`);
      process.exit(1);
    }

    const stage = STAGE_MAP[key];
    const variables = extractVariables(raw);

    inserts.push(
      `INSERT INTO prompts (tenant_id, key, stage, template, variables, model_params, version, is_active, is_default)
VALUES (NULL, '${sqlEscape(key)}', '${sqlEscape(stage)}', '${sqlEscape(raw)}', '${sqlJsonEscape(variables)}'::jsonb, '{}'::jsonb, 1, true, true)
ON CONFLICT DO NOTHING;`
    );
  }

  const sql = `-- AGORA · 07 · Засев дефолтных промптов (задача #26)
--
-- Идемпотентно: ON CONFLICT DO NOTHING. Повторный прогон не плодит строки и
-- не затирает пользовательские версии. Дефолты (tenant_id IS NULL) сеются здесь,
-- а не из-под agora_app — RLS-политика prompts_write_own_only требует
-- tenant_id = current_tenant(), а у дефолта он NULL. Эта миграция выполняется
-- от имени владельца, который обходит RLS (но FORCE RLS ловит и его, если
-- контекст не пуст; здесь контекст не устанавливается, и partial-индекс
-- prompts_default_key_uniq WHERE is_default гарантирует уникальность).
--
-- Файл сгенерирован скриптом apps/web/scripts/generate-prompts-seed.mjs.
-- НЕ редактируйте вручную — перегенерируйте: npm run prompts:seed:sql

${inserts.join("\n\n")}
`;

  await writeFile(OUT_FILE, sql, "utf8");
  console.log(`Сгенерировано ${inserts.length} INSERT → ${OUT_FILE}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});