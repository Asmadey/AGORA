import "server-only";

import type { PoolClient } from "pg";

/**
 * Резолвер промптов (задача #26).
 *
 * По ключу отдаёт активную версию арендатора, при её отсутствии — дефолт.
 * ОДИН запрос, а не два: порядок разрешения — часть контракта, и разносить его
 * по вызовам нельзя. RLS-политика prompts_read_own_and_defaults уже
 * фильтрует (tenant_id = current OR tenant_id IS NULL), остаётся лишь
 * выбрать правильную строку: ORDER BY tenant_id NULLS LAST LIMIT 1
 * предпочтёт строку арендатора, а дефолт возьмёт как fallback.
 *
 * ─── Почему именно так ────────────────────────────────────────────────────
 * Два запроса (сначала «найди своё», потом «дай дефолт») кажутся нагляднее,
 * но создают гонку: между запросами арендатор мог сохранить версию, или
 * активная могла быть деактивирована. Один запрос атомарен по построению.
 *
 * ORDER BY tenant_id NULLS LAST: NULL в Postgres сортируется первым при ASC,
 * последним — при NULLS LAST. Нам нужно «своё предпочтительнее дефолта»,
 * а своё — это NOT NULL, дефолт — NULL. Значит NULLS LAST ставит своё выше.
 *
 * is_active: у арендатора активна одна версия (уникальный индекс
 * prompts_tenant_key_active_uniq). Дефолт всегда is_active=true (миграция 07).
 * Фильтр is_active=true отсекает неактивные версии арендатора.
 */

export interface ResolvedPrompt {
  id: string;
  tenant_id: string | null;
  key: string;
  stage: string;
  template: string;
  variables: string[];
  model_params: Record<string, unknown>;
  version: number;
  is_active: boolean;
  is_default: boolean;
}

interface PromptRow {
  id: string;
  tenant_id: string | null;
  key: string;
  stage: string;
  template: string;
  variables: string[];
  model_params: Record<string, unknown>;
  version: number;
  is_active: boolean;
  is_default: boolean;
}

/**
 * Резолвит активный промпт по ключу для текущего арендатора.
 * Вызывается внутри withTenant — client уже имеет тенант-контекст.
 *
 * Возвращает null, если ключ не найден ни среди своих, ни среди дефолтов.
 */
export async function resolvePrompt(
  client: PoolClient,
  key: string,
): Promise<ResolvedPrompt | null> {
  const { rows } = await client.query<PromptRow>(
    `SELECT id, tenant_id, key, stage, template, variables, model_params,
            version, is_active, is_default
     FROM prompts
     WHERE key = $1 AND is_active = true
     ORDER BY tenant_id NULLS LAST
     LIMIT 1`,
    [key],
  );
  return rows[0] ?? null;
}

/**
 * Валидатор переменных (задача #26, кейс 11–12).
 *
 * Множество {{плейсхолдеров}} в template обязано совпадать с массивом variables.
 * Расхождение в любую сторону — отказ с перечислением:
 *   - необъявленная переменная → в модель уйдёт литеральная строка {{foo}};
 *   - объявленная, но неиспользуемая → вызывающий код передаёт данные в никуда.
 *
 * Возвращает null при совпадении, иначе объект с двумя списками расхождений.
 */
export function validateVariables(
  template: string,
  variables: string[],
): { undeclared: string[]; unused: string[] } | null {
  const inTemplate = extractPlaceholderNames(template);
  const declared = new Set(variables);
  const inTemplateSet = new Set(inTemplate);

  const undeclared = [...inTemplateSet].filter((v) => !declared.has(v));
  const unused = [...declared].filter((v) => !inTemplateSet.has(v));

  if (undeclared.length === 0 && unused.length === 0) return null;
  return { undeclared, unused };
}

/** Извлекает {{имена}} без повторов — та же логика, что в prompt-registry.ts. */
export function extractPlaceholderNames(text: string): string[] {
  const found = text.matchAll(/\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g);
  return [...new Set([...found].map((m) => m[1]))];
}

/**
 * Подстановка переменных в шаблон для dry-run (preview).
 * НЕ вызывает модель — только текстовая замена.
 * Возвращает null, если не все переменные получили значение.
 */
export function substituteVariables(
  template: string,
  values: Record<string, string>,
): { ok: true; text: string } | { ok: false; missing: string[] } {
  const names = extractPlaceholderNames(template);
  const missing = names.filter((n) => !(n in values) || values[n] === undefined || values[n] === null);
  if (missing.length > 0) return { ok: false, missing };

  let text = template;
  for (const name of names) {
    // Экранируем спецсимволы для regex, но имя переменной из [a-zA-Z0-9_.]
    // безопасно. Учитываем возможные пробелы вокруг имени.
    text = text.replace(new RegExp(`\\{\\{\\s*${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\}\\}`, "g"), values[name]);
  }
  return { ok: true, text };
}

// ─── Типы данных промптов для API ─────────────────────────────────────────

export interface PromptVersion {
  id: string;
  tenant_id: string | null;
  key: string;
  stage: string;
  template: string;
  variables: string[];
  model_params: Record<string, unknown>;
  version: number;
  is_active: boolean;
  is_default: boolean;
  created_at: string;
}

interface PromptVersionRow {
  id: string;
  tenant_id: string | null;
  key: string;
  stage: string;
  template: string;
  variables: string[];
  model_params: Record<string, unknown>;
  version: number;
  is_active: boolean;
  is_default: boolean;
  created_at: Date;
}

function rowToVersion(row: PromptVersionRow): PromptVersion {
  return {
    id: row.id,
    tenant_id: row.tenant_id,
    key: row.key,
    stage: row.stage,
    template: row.template,
    variables: row.variables,
    model_params: row.model_params,
    version: row.version,
    is_active: row.is_active,
    is_default: row.is_default,
    created_at: row.created_at.toISOString(),
  };
}

/**
 * Список активных промптов по стадиям.
 * Использует тот же ORDER BY tenant_id NULLS LAST — для каждого ключа
 * берётся активная версия арендатора или дефолт.
 */
export async function listActivePromptsByStage(
  client: PoolClient,
): Promise<Record<string, PromptVersion[]>> {
  // DISTINCT ON (key) + ORDER BY key, tenant_id NULLS LAST — ровно та же
  // логика, что в resolvePrompt, но для всех ключей сразу.
  const { rows } = await client.query<PromptVersionRow>(
    `SELECT DISTINCT ON (key) id, tenant_id, key, stage, template, variables,
           model_params, version, is_active, is_default, created_at
     FROM prompts
     WHERE is_active = true
     ORDER BY key, tenant_id NULLS LAST`,
  );

  const byStage: Record<string, PromptVersion[]> = {};
  for (const row of rows) {
    const v = rowToVersion(row);
    if (!byStage[v.stage]) byStage[v.stage] = [];
    byStage[v.stage].push(v);
  }
  return byStage;
}

/**
 * История версий одного ключа: активная + все версии арендатора + дефолт.
 */
export async function getPromptWithHistory(
  client: PoolClient,
  key: string,
): Promise<{ active: PromptVersion | null; history: PromptVersion[] }> {
  // Активная версия (та же логика, что в resolvePrompt)
  const active = await resolvePrompt(client, key);

  // Все версии: дефолт + свои
  const { rows } = await client.query<PromptVersionRow>(
    `SELECT id, tenant_id, key, stage, template, variables, model_params,
            version, is_active, is_default, created_at
     FROM prompts
     WHERE key = $1
     ORDER BY tenant_id NULLS LAST, version DESC`,
    [key],
  );

  return {
    active: active
      ? {
          id: active.id,
          tenant_id: active.tenant_id,
          key: active.key,
          stage: active.stage,
          template: active.template,
          variables: active.variables,
          model_params: active.model_params,
          version: active.version,
          is_active: active.is_active,
          is_default: active.is_default,
          created_at: rows.find((r) => r.id === active.id)?.created_at.toISOString() ?? new Date().toISOString(),
        }
      : null,
    history: rows.map(rowToVersion),
  };
}