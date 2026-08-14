#!/usr/bin/env node
/**
 * Засев корпуса в базу (этап Е).
 *
 * ─── Почему скрипт, а не миграция ──────────────────────────────────────────
 * Миграция меняет СХЕМУ (§5 CLAUDE.md) — и меняет её для всех арендаторов
 * сразу. Корпус же принадлежит команде: `corpus_datasets.tenant_id` не бывает
 * пустым, и вписать его в миграцию нечем — на момент применения миграции команд
 * может не быть вовсе.
 *
 * Вторая причина практическая: 165 записей по 47 ответов анкеты — это 1.8 МБ.
 * Вшитые в SQL, они попали бы в каждый прогон `migrate.sh` и в каждый дифф
 * репозитория, при том что содержимое уже лежит в
 * `data/grounding/unified_respondent_sessions.json`.
 *
 * Скрипт идемпотентен: повторный запуск обновляет записи по respondent_id, а не
 * заводит вторые. Датасет ищется по имени внутри команды.
 *
 * Запуск:
 *   set -a; source .env.local; set +a
 *   node apps/web/scripts/seed-corpus.mjs --team-id <uuid>
 *   node apps/web/scripts/seed-corpus.mjs --team-id <uuid> --name "Сериалы 2025" --file путь.json
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { parseArgs } from "node:util";

import pg from "pg";

const { values } = parseArgs({
  options: {
    "team-id": { type: "string" },
    name: { type: "string", default: "Базовый корпус" },
    file: { type: "string" },
    description: { type: "string" },
  },
});

if (!values["team-id"]) {
  console.error("нужен --team-id: корпус принадлежит команде, а не установке");
  process.exit(2);
}

// process.cwd() при запуске из корня монорепо — сам корень; из apps/web — apps/web.
// Оба варианта законны, поэтому файл ищется по обоим, а не по одному.
function corpusPath() {
  if (values.file) return path.resolve(values.file);
  const relative = "data/grounding/unified_respondent_sessions.json";
  for (const base of [process.cwd(), path.resolve(process.cwd(), "../..")]) {
    const candidate = path.join(base, relative);
    try {
      readFileSync(candidate);
      return candidate;
    } catch {
      // следующий вариант раскладки
    }
  }
  console.error(`не найден ${relative} — укажите --file`);
  process.exit(2);
}

// Сертификат передаётся параметром строки подключения, а не полем ssl: pg
// собирает конфигурацию как Object.assign({}, config, parse(connectionString)),
// и разобранная строка затирает явно заданный ssl. То же в seed-auth.mjs.
function dsn() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    console.error("DATABASE_URL не задан: сделайте `set -a; source .env.local; set +a`");
    process.exit(2);
  }
  const caPath = process.env.PGSSLROOTCERT;
  if (!caPath || url.includes("sslrootcert=")) return url;
  return `${url}${url.includes("?") ? "&" : "?"}sslrootcert=${encodeURIComponent(caPath)}`;
}

const file = corpusPath();
const sessions = JSON.parse(readFileSync(file, "utf-8"));
if (!Array.isArray(sessions) || sessions.length === 0) {
  console.error(`${file}: ожидался непустой массив записей`);
  process.exit(2);
}

const teamId = values["team-id"];
const client = new pg.Client({ connectionString: dsn() });

await client.connect();
try {
  await client.query("BEGIN");
  await client.query("SET LOCAL ROLE agora_app");
  await client.query("SELECT set_config('app.tenant_id', $1, true)", [teamId]);

  const { rows } = await client.query(
    `INSERT INTO corpus_datasets (tenant_id, name, description, source)
     VALUES (app.current_tenant(), $1, $2, $3)
     ON CONFLICT (tenant_id, name)
     DO UPDATE SET description = EXCLUDED.description,
                   source = EXCLUDED.source,
                   updated_at = now()
     RETURNING id`,
    [
      values.name,
      values.description ?? `Засев из ${path.basename(file)}`,
      path.basename(file),
    ],
  );
  const datasetId = rows[0].id;

  let written = 0;
  let skipped = 0;
  for (const session of sessions) {
    const respondentId = session?.respondent_id;
    if (typeof respondentId !== "string" || !respondentId) {
      // Запись без идентификатора пропускается вслух: молча она превратилась бы
      // в недостающего респондента, а доли считаются по числу записей.
      skipped += 1;
      continue;
    }
    await client.query(
      `INSERT INTO corpus_records (tenant_id, dataset_id, respondent_id, data)
       VALUES (app.current_tenant(), $1, $2, $3)
       ON CONFLICT (dataset_id, respondent_id)
       DO UPDATE SET data = EXCLUDED.data, updated_at = now()`,
      [datasetId, respondentId, JSON.stringify(session)],
    );
    written += 1;
  }

  await client.query("COMMIT");
  console.log(
    `датасет «${values.name}» (${datasetId}): записано ${written}` +
      (skipped ? `, пропущено без respondent_id: ${skipped}` : ""),
  );
} catch (error) {
  await client.query("ROLLBACK");
  console.error(error.message);
  process.exitCode = 1;
} finally {
  await client.end();
}
