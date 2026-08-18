import "server-only";

import type { PoolClient } from "pg";

/**
 * Корпус в базе: датасеты, записи и слепки (этап Е).
 *
 * ─── Чем это отличается от lib/server/corpus.ts ────────────────────────────
 * Тот модуль читает файл `data/grounding/unified_respondent_sessions.json` и
 * отвечает на вопрос «покрыт ли выбранный сегмент корпусом» на шаге
 * «Аудитория». Он read-only и общий для всех арендаторов.
 *
 * Здесь — редактируемый корпус арендатора, из которого снимается слепок при
 * создании аудитории. Два модуля живут рядом временно: файл остаётся
 * источником засева, а метрики заземления переедут на датасет следующим шагом.
 * Пока они разъезжаются только в одном месте — если корпус отредактировали, —
 * и это видно по числу записей на экране раздела.
 *
 * ─── Почему слепок снимается при создании аудитории ────────────────────────
 * Корпус читается ровно один раз: когда генератор сэмплирует персон по долям.
 * Слепок в момент запуска исследования опоздал бы — персоны к этому моменту уже
 * собраны, и слепок описывал бы корпус, по которому их не собирали.
 *
 * Ссылка живёт на наборе персон (`persona_sets.corpus_snapshot_id`), а
 * исследование показывает версию корпуса через свой набор — то есть через то
 * звено, где корпус действительно применялся.
 */

export interface CorpusDataset {
  id: string;
  name: string;
  description: string | null;
  source: string | null;
  /** Сколько записей сейчас. Считается запросом, а не хранится: см. ниже. */
  recordsCount: number;
  updatedAt: string;
}

export interface CorpusRecord {
  id: string;
  respondentId: string;
  data: Record<string, unknown>;
  updatedAt: string;
}

export interface CorpusSnapshot {
  id: string;
  datasetId: string | null;
  datasetName: string;
  recordsCount: number;
  sha256: string;
  createdAt: string;
}

/**
 * Датасеты арендатора с числом записей.
 *
 * Счётчик считается запросом, а не хранится колонкой. Хранимый счётчик надо
 * поддерживать при каждой правке, удалении и засеве, и расходится он молча:
 * на экране «165 записей», в выборке 164, и объяснить разницу нечем. Датасетов
 * единицы, записей сотни — COUNT здесь бесплатен.
 */
export async function listDatasets(client: PoolClient): Promise<CorpusDataset[]> {
  const { rows } = await client.query<{
    id: string;
    name: string;
    description: string | null;
    source: string | null;
    records_count: string;
    updated_at: Date;
  }>(
    `SELECT d.id, d.name, d.description, d.source, d.updated_at,
            (SELECT COUNT(*) FROM corpus_records r WHERE r.dataset_id = d.id) AS records_count
     FROM corpus_datasets d
     ORDER BY d.name`,
  );
  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    description: r.description,
    source: r.source,
    recordsCount: Number(r.records_count),
    updatedAt: r.updated_at.toISOString(),
  }));
}

/** Записи датасета страницей. Порядок устойчивый — иначе пагинация повторяется. */
export async function listRecords(
  client: PoolClient,
  datasetId: string,
  options: { limit?: number; offset?: number } = {},
): Promise<{ items: CorpusRecord[]; total: number }> {
  const limit = Math.min(Math.max(options.limit ?? 50, 1), 200);
  const offset = Math.max(options.offset ?? 0, 0);

  const { rows } = await client.query<{
    id: string;
    respondent_id: string;
    data: Record<string, unknown>;
    updated_at: Date;
    total: string;
  }>(
    `SELECT id, respondent_id, data, updated_at,
            COUNT(*) OVER () AS total
     FROM corpus_records
     WHERE dataset_id = $1
     ORDER BY respondent_id
     LIMIT $2 OFFSET $3`,
    [datasetId, limit, offset],
  );

  return {
    items: rows.map((r) => ({
      id: r.id,
      respondentId: r.respondent_id,
      data: r.data,
      updatedAt: r.updated_at.toISOString(),
    })),
    total: rows[0] ? Number(rows[0].total) : 0,
  };
}

export async function upsertRecord(
  client: PoolClient,
  datasetId: string,
  respondentId: string,
  data: Record<string, unknown>,
): Promise<CorpusRecord> {
  const { rows } = await client.query<{
    id: string;
    respondent_id: string;
    data: Record<string, unknown>;
    updated_at: Date;
  }>(
    `INSERT INTO corpus_records (tenant_id, dataset_id, respondent_id, data)
     VALUES (app.current_tenant(), $1, $2, $3)
     ON CONFLICT (dataset_id, respondent_id)
     DO UPDATE SET data = EXCLUDED.data, updated_at = now()
     RETURNING id, respondent_id, data, updated_at`,
    [datasetId, respondentId, JSON.stringify(data)],
  );
  const row = rows[0];
  return {
    id: row.id,
    respondentId: row.respondent_id,
    data: row.data,
    updatedAt: row.updated_at.toISOString(),
  };
}

/** Удаляет запись. `false` — записи не было либо она чужая (RLS их не различает). */
export async function deleteRecord(
  client: PoolClient,
  recordId: string,
): Promise<boolean> {
  const { rowCount } = await client.query(
    "DELETE FROM corpus_records WHERE id = $1",
    [recordId],
  );
  return (rowCount ?? 0) > 0;
}

/**
 * Контрольная сумма слепка считается в SQL, а не здесь.
 *
 * ─── Почему именно так ─────────────────────────────────────────────────────
 * Слепок пишет веб, а читает воркер — то есть TypeScript и Python. Каноническое
 * представление, написанное в обоих, разойдётся на первой же мелочи: где-то
 * `7` против `7.0`, где-то экранирование юникода, где-то порядок ключей. И
 * разойдётся молча — сумма перестанет совпадать у совершенно исправного
 * слепка, а объяснить это будет нечем.
 *
 * Поэтому сумма считается `encode(digest(records::text, 'sha256'), 'hex')` —
 * то есть Postgres по своей нормализованной форме jsonb. Обе стороны читают
 * одно определение, и сравнивать им нечего, кроме готовой строки.
 *
 * Ровно эту ошибку и должна была ловить функция `dataset_sha256()` в воркере,
 * которую не вызывал никто: расхождение содержимого с паспортом видел только
 * eval-тест.
 */

/**
 * Снимает слепок датасета целиком. Возвращает его идентификатор.
 *
 * Записи копируются в jsonb, а не связываются ссылками: смысл слепка в том,
 * чтобы пережить правку и удаление записей. Слепок из ссылок разъехался бы с
 * реальностью ровно в тот момент, ради которого заведён.
 *
 * Пустой датасет слепка не даёт: аудитория, собранная по нулю респондентов, —
 * это персоны из ниоткуда, и заземление на них было бы словом без содержания.
 */
export async function createSnapshot(
  client: PoolClient,
  datasetId: string,
): Promise<CorpusSnapshot> {
  const { rows: datasetRows } = await client.query<{ name: string }>(
    "SELECT name FROM corpus_datasets WHERE id = $1",
    [datasetId],
  );
  const dataset = datasetRows[0];
  if (!dataset) throw new Error("датасет не найден");

  const { rows: recordRows } = await client.query<{
    respondent_id: string;
    data: Record<string, unknown>;
  }>(
    "SELECT respondent_id, data FROM corpus_records WHERE dataset_id = $1 ORDER BY respondent_id",
    [datasetId],
  );
  if (recordRows.length === 0) {
    throw new Error(
      `датасет «${dataset.name}» пуст: собирать аудиторию не из чего — ` +
        `персоны сэмплируются по долям корпуса, а долей нет`,
    );
  }

  const { rows } = await client.query<{ id: string; created_at: Date; sha256: string }>(
    `INSERT INTO corpus_snapshots
       (tenant_id, dataset_id, dataset_name, records, records_count, sha256)
     VALUES (app.current_tenant(), $1, $2, $3::jsonb, $4,
             encode(digest($3::jsonb::text, 'sha256'), 'hex'))
     RETURNING id, created_at, sha256`,
    [
      datasetId,
      dataset.name,
      JSON.stringify(recordRows.map((r) => r.data)),
      recordRows.length,
    ],
  );

  return {
    id: rows[0].id,
    datasetId,
    datasetName: dataset.name,
    recordsCount: recordRows.length,
    sha256: rows[0].sha256,
    createdAt: rows[0].created_at.toISOString(),
  };
}

/** Слепок набора персон. null — набор собран до появления слепков либо из файла. */
/**
 * Записи слепка, по которому собран набор.
 *
 * Отдельно от `snapshotOfPersonaSet`: тот отдаёт паспорт слепка (имя, размер,
 * контрольную сумму) и зовётся на каждый показ набора, а записи — это весь
 * корпус целиком, и тянуть его ради шапки было бы расточительством.
 *
 * Берётся именно слепок, а не датасет на сегодня: датасет правят, и сравнение с
 * его текущей версией отвечало бы на другой вопрос — «похож ли старый набор на
 * новые данные».
 */
export async function snapshotRecordsOfPersonaSet(
  client: PoolClient,
  personaSetId: string,
): Promise<Record<string, unknown>[]> {
  const { rows } = await client.query<{ records: unknown }>(
    `SELECT s.records
     FROM corpus_snapshots s
     JOIN persona_sets p ON p.corpus_snapshot_id = s.id
     WHERE p.id = $1`,
    [personaSetId],
  );
  const records = rows[0]?.records;
  return Array.isArray(records) ? (records as Record<string, unknown>[]) : [];
}

export async function snapshotOfPersonaSet(
  client: PoolClient,
  personaSetId: string,
): Promise<CorpusSnapshot | null> {
  const { rows } = await client.query<{
    id: string;
    dataset_id: string | null;
    dataset_name: string;
    records_count: number;
    sha256: string;
    created_at: Date;
  }>(
    `SELECT s.id, s.dataset_id, s.dataset_name, s.records_count, s.sha256, s.created_at
     FROM corpus_snapshots s
     JOIN persona_sets p ON p.corpus_snapshot_id = s.id
     WHERE p.id = $1`,
    [personaSetId],
  );
  const row = rows[0];
  if (!row) return null;
  return {
    id: row.id,
    datasetId: row.dataset_id,
    datasetName: row.dataset_name,
    recordsCount: row.records_count,
    sha256: row.sha256,
    createdAt: row.created_at.toISOString(),
  };
}
