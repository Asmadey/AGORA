import "server-only";

import { createHash } from "node:crypto";

import type { PoolClient } from "pg";

import { listActivePromptsByStage } from "@/lib/server/prompts";
import { DEFAULT_SETTINGS, DEFAULT_TEMPERATURES, TEMPERATURE_STAGES } from "@/lib/settings";

/**
 * Запуск исследования (задача #11).
 *
 * ─── Снимок промптов ───────────────────────────────────────────────────────
 * Decision Log #10. Промпты правятся в Промпт-студии между прогонами, и без
 * пиннинга версий отчёт невоспроизводим: перезапуск того же исследования пошёл
 * бы по другим инструкциям, а объяснить расхождение было бы нечем.
 *
 * Снимок берётся из АКТИВНЫХ версий в базе, а не из файлов `prompts/`: файлы —
 * это seed, а активной может быть версия арендатора, отредактированная в
 * студии. Читать файлы значило бы пиннить то, что не исполняется.
 *
 * ─── Идемпотентность ───────────────────────────────────────────────────────
 * Не «похожий результат», а «не создаёт вторую задачу». Запуск платный: разбор
 * кадров и прогон респондентов стоят денег при каждом вызове, а двойной клик,
 * ретрай прокси или обновление страницы неотличимы от намеренного повтора.
 *
 * Ключ — отпечаток параметров, включая seed и снимок промптов. Снимок в ключе
 * обязателен: если промпт отредактировали между двумя нажатиями, это уже другой
 * прогон, и склеивать его с прежним нельзя — результат будет другим.
 */

export interface LaunchParams {
  /** Имя файла, как его назвал пользователь. Для показа, не для доступа. */
  sourceName?: string | null;
  /**
   * Название исследования, заданное человеком на шаге «Резюме».
   *
   * Отдельно от `sourceName`: имя файла — факт о загрузке, название — то, зачем
   * работа делалась. Держать их в одном поле значит терять исходник при первой
   * же правке названия.
   */
  title?: string | null;
  mode: "short" | "long";
  videoRef: string | null;
  personaSetId: string | null;
  surveyId: string | null;
  projectId: string | null;
  replicationCount: number;
  seed: number;
  /**
   * Дополнительный контекст об аудитории из приложенного .txt/.md (#31).
   *
   * Уезжает в системный промпт каждой персоны. Проверен и обрезан до потолка
   * ещё в маршруте — сюда приходит готовый текст либо null.
   */
  audienceContext?: string | null;
}

export interface LaunchedTask {
  id: string;
  /**
   * Человеческий номер исследования в пределах команды.
   *
   * UUID остаётся ключом и остаётся в адресе — он уникален глобально. Но в
   * разговоре им не пользуются: «посмотри e81feb92-97a2-43ad…» не произносится
   * вслух и не набирается по памяти. `null` — задача создана до появления
   * нумерации и номер ей не раздали.
   */
  seqNo: number | null;
  mode: string;
  /**
   * Имя файла, как его назвал пользователь. `null` — прогон старше миграции 30
   * либо файл загружен в обход визарда; тогда показывается ключ S3.
   */
  sourceName: string | null;
  /**
   * Название, заданное человеком. `null` — не задавали; тогда на экране
   * показывается имя файла (см. lib/research-title.ts).
   */
  title: string | null;
  /** Ключ S3 кадра-заставки. `null` — кадров нет. */
  posterRef: string | null;
  videoRef: string | null;
  replicationCount: number;
  promptsSnapshot: Record<string, PinnedPrompt>;
  /**
   * Настройки команды на момент запуска: жёсткий кап вызовов VLM и прочее.
   *
   * Снимок по той же причине, что и промпты: пока задача стоит в очереди, кап
   * можно сменить, и тогда часть панелей разобрана под одним потолком, часть
   * под другим. Разница в полноте разбора выглядела бы свойством материала.
   */
  settingsSnapshot: Record<string, unknown>;
  status: string;
  createdAt: string;
  /** Кто запустил. `null` — автора удалили из команды. */
  author: string | null;
  /** false — задача уже существовала, повторный запуск ничего не создал. */
  created: boolean;
}

/**
 * Номер исследования для человека: `№ 0007`.
 *
 * Четыре знака — не про ожидаемое число прогонов, а про выравнивание в столбце:
 * список, где «7» и «112» стоят под разной шириной, читается хуже, чем список с
 * ведущими нулями. При пятизначном номере строка просто станет длиннее.
 *
 * `null` — задача создана до появления нумерации. Показывать вместо неё «0000»
 * значило бы выдумать номер, которого нет.
 */
export function taskNumber(seqNo: number | null): string | null {
  return seqNo === null ? null : `№ ${String(seqNo).padStart(4, "0")}`;
}

export interface PinnedPrompt {
  id: string;
  version: number;
  /** Отпечаток шаблона: по нему видно, что версия не подменена на месте. */
  templateSha256: string;
}

interface TaskRow {
  id: string;
  seq_no: number | null;
  mode: string;
  video_ref: string | null;
  source_name: string | null;
  title: string | null;
  poster_ref: string | null;
  replication_count: number;
  prompts_snapshot: Record<string, PinnedPrompt>;
  status: string;
  created_at: Date;
  author: string | null;
  settings_snapshot: Record<string, unknown>;
}

/**
 * Снимок активных версий всех ключей реестра.
 *
 * Пустой снимок — это отказ, а не «промптов нет». Пустой снимок означает
 * «пиннинг есть в схеме, но не работает», и от рабочего он неотличим до первой
 * правки промпта — то есть до момента, когда воспроизводимость уже потеряна.
 */
export async function buildPromptsSnapshot(
  client: PoolClient,
): Promise<Record<string, PinnedPrompt>> {
  const byStage = await listActivePromptsByStage(client);
  const snapshot: Record<string, PinnedPrompt> = {};

  for (const versions of Object.values(byStage)) {
    for (const v of versions) {
      snapshot[v.key] = {
        id: v.id,
        version: v.version,
        templateSha256: createHash("sha256").update(v.template).digest("hex"),
      };
    }
  }

  if (Object.keys(snapshot).length === 0) {
    throw new Error(
      "реестр промптов пуст: снимок собрать не из чего. Примените миграцию " +
        "07_prompts_seed.sql — без снимка прогон невоспроизводим (Decision Log #10)",
    );
  }
  return snapshot;
}

/**
 * Настройки команды на момент запуска, в форме, которую читает воркер.
 *
 * ─── Почему это вообще понадобилось ────────────────────────────────────────
 * Жёсткий кап вызовов VLM жил в двух местах сразу: в интерфейсе, где его
 * выставляют, и в `CallBudget.for_task`, который умеет его применить. Между
 * ними не было ничего — воркер получал в очереди снимок промптов и не получал
 * настроек, а `analyze_panels` звался без бюджета. Настройка была, ограничения
 * не было, и отличить одно от другого можно было только по счёту провайдера.
 *
 * Форма полей совпадает с `lib/settings.ts` и с тем, что читает воркер:
 * costCap ∈ {auto, hard}, costCapValue осмыслен только при hard. Отсутствие
 * строки настроек — законное состояние (команда их ни разу не сохраняла), и
 * означает «авто», то есть без потолка.
 */
export async function buildSettingsSnapshot(
  client: PoolClient,
): Promise<Record<string, unknown>> {
  const { rows } = await client.query<{
    cost_cap_calls: number | null;
    whisper_model: string;
    provider_config: Record<string, unknown> | null;
  }>(
    "SELECT cost_cap_calls, whisper_model, provider_config FROM settings WHERE tenant_id = current_setting('app.tenant_id')::uuid",
  );
  const row = rows[0];
  // Температуры пиннятся на прогон по той же причине, что кап вызовов и версии
  // промптов: пока задача стоит в очереди, команда может их сменить. Тогда
  // персоны созданы под одной температурой, опрошены под другой, а разница в
  // разбросе ответов выглядела бы свойством материала, а не настройки.
  const temperatures = normalizeTemperatures(row?.provider_config);
  // Выбор моделей и режим рассуждения пиннятся вместе с остальным: сменив
  // модель, пока задача стоит в очереди, команда получила бы отчёт, у которого
  // в карточке одна модель, а считала его другая.
  const provider = pickProvider(row?.provider_config);
  const requestionCap = pickRequestionCap(row?.provider_config);
  if (!row) return { costCap: "auto", temperatures, requestionCap, ...provider };
  return row.cost_cap_calls === null
    ? { costCap: "auto", whisperModel: row.whisper_model, temperatures, requestionCap, ...provider }
    : {
        costCap: "hard",
        costCapValue: row.cost_cap_calls,
        whisperModel: row.whisper_model,
        temperatures,
        requestionCap,
        ...provider,
      };
}

/**
 * Поля провайдера для снимка: модели, рассуждение, адрес.
 *
 * Ключа здесь нет и быть не должно. Снимок живёт столько же, сколько отчёт, и
 * копия ключа в каждой строке `tasks` — это тот же секрет, размноженный по
 * резервным копиям базы без единого способа его отозвать.
 */
/**
 * Потолок переспроса из настроек команды.
 *
 * Пиннится в снимок вместе с остальным: пока задача стоит в очереди, настройку
 * можно сменить, и тогда часть забракованных ответов переспрошена, часть нет —
 * внутри одного прогона, который потом читают как целое.
 */
function pickRequestionCap(providerConfig: unknown): number {
  const stored = (providerConfig ?? {}) as { requestionCap?: unknown };
  return typeof stored.requestionCap === "number" && Number.isInteger(stored.requestionCap)
    ? stored.requestionCap
    : DEFAULT_SETTINGS.requestionCap;
}

function pickProvider(
  providerConfig: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const stored = providerConfig ?? {};
  const out: Record<string, unknown> = {};
  for (const key of ["models", "reasoning", "judgeReasoning", "endpoint"]) {
    if (stored[key] !== undefined) out[key] = stored[key];
  }
  return out;
}

/**
 * Температуры из `provider_config`, дополненные умолчаниями.
 *
 * Снимок обязан быть ПОЛНЫМ: воркер читает стадию по имени, и отсутствующее
 * поле там означало бы «умолчание воркера», а не «умолчание настроек». Два
 * умолчания в разных местах — это ровно тот случай, когда они однажды
 * разойдутся, и никто не поймёт, какое из них действовало.
 */
function normalizeTemperatures(
  providerConfig: Record<string, unknown> | null | undefined,
): Record<string, number> {
  const stored = (providerConfig ?? {}) as { temperatures?: unknown };
  const raw = (stored.temperatures ?? {}) as Record<string, unknown>;
  const result: Record<string, number> = { ...DEFAULT_TEMPERATURES };
  for (const stage of TEMPERATURE_STAGES) {
    const value = raw[stage.key];
    if (typeof value === "number" && Number.isFinite(value)) {
      result[stage.key] = value;
    }
  }
  return result;
}

/**
 * Отпечаток запуска. Одинаковые параметры → одинаковый ключ → та же задача.
 *
 * tenant_id в ключ НЕ входит: он отдельной колонкой в уникальном индексе.
 * Смешивать их в одну строку значило бы полагаться на то, что хеш не совпадёт
 * у разных арендаторов, вместо того чтобы разделить их структурно.
 */
export function idempotencyKey(
  params: LaunchParams,
  snapshot: Record<string, PinnedPrompt>,
): string {
  const canonical = JSON.stringify({
    mode: params.mode,
    videoRef: params.videoRef,
    personaSetId: params.personaSetId,
    surveyId: params.surveyId,
    projectId: params.projectId,
    replicationCount: params.replicationCount,
    seed: params.seed,
    // Сортировка обязательна: порядок ключей объекта в JS зависит от порядка
    // вставки, а он приходит из порядка строк базы и не гарантирован.
    prompts: Object.keys(snapshot)
      .sort()
      .map((k) => [k, snapshot[k].id, snapshot[k].version, snapshot[k].templateSha256]),
  });
  return createHash("sha256").update(canonical).digest("hex");
}

function toTask(row: TaskRow, created: boolean): LaunchedTask {
  return {
    id: row.id,
    seqNo: row.seq_no ?? null,
    sourceName: row.source_name ?? null,
    title: row.title ?? null,
    posterRef: row.poster_ref ?? null,
    mode: row.mode,
    videoRef: row.video_ref,
    replicationCount: row.replication_count,
    promptsSnapshot: row.prompts_snapshot,
    settingsSnapshot: row.settings_snapshot ?? {},
    status: row.status,
    createdAt: row.created_at.toISOString(),
    author: row.author,
    created,
  };
}

/**
 * Создаёт задачу либо возвращает уже существующую с тем же ключом.
 *
 * ON CONFLICT DO NOTHING + повторный SELECT, а не «сначала посмотреть, потом
 * вставить»: проверка перед вставкой гонку не закрывает — два одновременных
 * запроса оба ничего не находят и оба вставляют. Здесь конфликт разрешает
 * уникальный индекс, то есть база, а не порядок исполнения.
 */
export async function launchTask(
  client: PoolClient,
  params: LaunchParams,
  createdBy: string | null,
): Promise<LaunchedTask> {
  // ─── Проект обязан принадлежать этому же арендатору ───────────────────────
  //
  // Внешний ключ `tasks.project_id REFERENCES projects(id)` этого НЕ проверяет:
  // Postgres выполняет проверки ссылочной целостности в обход RLS, то есть
  // чужой проект для неё существует. Пока визард не отправлял projectId, путь
  // был недостижим; теперь отправляет.
  //
  // Проверка идёт SELECT'ом под RLS: чужая строка политике не видна, и запрос
  // честно возвращает ноль. Молча заменить на NULL было бы хуже отказа —
  // исследование ушло бы «в никуда», а оператор считал бы, что подшил его.
  if (params.projectId) {
    const { rowCount } = await client.query(
      "SELECT 1 FROM projects WHERE id = $1",
      [params.projectId],
    );
    if (!rowCount) {
      throw new Error(`проект ${params.projectId} не найден у этой команды`);
    }
  }

  const snapshot = await buildPromptsSnapshot(client);
  const settings = await buildSettingsSnapshot(client);
  // Контекст аудитории пиннится вместе с настройками, а не читается на лету:
  // он часть того, ЧТО спросили у персон, и меняться между постановкой задачи
  // и её исполнением не должен — иначе половина ответов дана с ним, половина без.
  if (params.audienceContext) {
    settings.audienceContext = params.audienceContext;
  }
  const key = idempotencyKey(params, snapshot);

  const inserted = await client.query<TaskRow>(
    `WITH next AS (
       -- Номер берётся счётчиком арендатора в ТОЙ ЖЕ транзакции, что и вставка.
       -- Sequence не годится: он не откатывается вместе с транзакцией, и
       -- отменённое создание съедало бы номер навсегда. Пропуск в нумерации
       -- выглядит потерянным исследованием, и объяснять его пришлось бы каждому
       -- новому человеку в команде.
       --
       -- Цена — блокировка одной строки счётчика на время вставки. Исследование
       -- создаёт человек руками, десятки раз в день на команду: очередь на этой
       -- строке не соберётся.
       INSERT INTO tenant_counters (tenant_id, kind, value)
       VALUES (current_setting('app.tenant_id')::uuid, 'task', 1)
       ON CONFLICT (tenant_id, kind)
       DO UPDATE SET value = tenant_counters.value + 1
       RETURNING value
     )
     INSERT INTO tasks (project_id, persona_set_id, survey_id, mode, video_ref,
                        replication_count, prompts_snapshot, settings_snapshot,
                        idempotency_key, created_by, tenant_id, seq_no, source_name, title)
     SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
             current_setting('app.tenant_id')::uuid, next.value, $11, $12
     FROM next
     ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL
     DO NOTHING
     RETURNING id, seq_no, mode, video_ref, source_name, title, poster_ref, replication_count, prompts_snapshot, settings_snapshot, status, created_at, (SELECT COALESCE(u.name, u.email) FROM users u WHERE u.id = tasks.created_by) AS author`,
    [
      params.projectId,
      params.personaSetId,
      params.surveyId,
      params.mode,
      params.videoRef,
      params.replicationCount,
      JSON.stringify(snapshot),
      JSON.stringify(settings),
      key,
      createdBy,
      params.sourceName ?? null,
      params.title ?? null,
    ],
  );

  if (inserted.rows.length > 0) return toTask(inserted.rows[0], true);

  // Конфликт: задача с таким ключом уже есть. Возвращаем её, а не ошибку —
  // для вызывающего повторный запуск обязан выглядеть как успешный.
  const existing = await client.query<TaskRow>(
    `SELECT id, seq_no, mode, video_ref, source_name, title, poster_ref, replication_count, prompts_snapshot, settings_snapshot, status, created_at, (SELECT COALESCE(u.name, u.email) FROM users u WHERE u.id = tasks.created_by) AS author
     FROM tasks WHERE idempotency_key = $1`,
    [key],
  );
  if (existing.rows.length === 0) {
    // Сюда попадём, только если строку удалили между INSERT и SELECT, либо если
    // RLS её не показывает. Молчать нельзя: пустой ответ выглядел бы как
    // «запуск прошёл», а задачи нет.
    throw new Error(
      "задача с этим ключом идемпотентности не создана и не найдена — " +
        "проверьте тенант-контекст и политику RLS на tasks",
    );
  }
  return toTask(existing.rows[0], false);
}

export interface RunTiming {
  /** Сколько шёл прогон целиком, в секундах. null — не запускался или не завершён. */
  totalSec: number | null;
  /** Длительность по этапам: [{node, durationSec}]. Пусто у прогонов до #В. */
  nodes: { node: string; durationSec: number | null; status: string }[];
}

/**
 * Сколько занял прогон и его этапы.
 *
 * ─── Откуда числа ──────────────────────────────────────────────────────────
 * `started_at` и `finished_at` ставит воркер при смене статуса; разбивка по
 * этапам приезжает в `progress` в конце прогона (`_save_timings`). До этого
 * колонка `progress` была заведена в схеме и не писалась никем, а снимок
 * прогресса в Valkey перезаписывался на каждое событие — то есть длительность
 * этапа не хранилась нигде, и «Время обработки» показывать было нечем.
 *
 * Пустая разбивка при непустом `totalSec` — это прогон, сделанный до появления
 * замеров. Показывать вместо неё нули значило бы утверждать, что этапы прошли
 * мгновенно.
 */
export async function loadRunTiming(
  client: PoolClient,
  id: string,
): Promise<RunTiming> {
  const { rows } = await client.query<{
    started_at: Date | null;
    finished_at: Date | null;
    progress: { timings?: unknown } | null;
  }>("SELECT started_at, finished_at, progress FROM tasks WHERE id = $1", [id]);

  const row = rows[0];
  if (!row) return { totalSec: null, nodes: [] };

  const totalSec =
    row.started_at && row.finished_at
      ? (row.finished_at.getTime() - row.started_at.getTime()) / 1000
      : null;

  const raw = Array.isArray(row.progress?.timings) ? row.progress.timings : [];
  const nodes = raw.flatMap((item) => {
    const entry = (item ?? {}) as Record<string, unknown>;
    const node = typeof entry.node === "string" ? entry.node : null;
    if (!node) return [];
    return [{
      node,
      durationSec:
        typeof entry.duration_sec === "number" && Number.isFinite(entry.duration_sec)
          ? entry.duration_sec
          : null,
      status: typeof entry.status === "string" ? entry.status : "неизвестно",
    }];
  });

  return { totalSec, nodes };
}

export async function getTask(
  client: PoolClient,
  id: string,
): Promise<LaunchedTask | null> {
  const { rows } = await client.query<TaskRow>(
    `SELECT id, seq_no, mode, video_ref, source_name, title, poster_ref, replication_count, prompts_snapshot, settings_snapshot, status, created_at, (SELECT COALESCE(u.name, u.email) FROM users u WHERE u.id = tasks.created_by) AS author
     FROM tasks WHERE id = $1`,
    [id],
  );
  return rows[0] ? toTask(rows[0], false) : null;
}

export async function listTasks(client: PoolClient): Promise<LaunchedTask[]> {
  const { rows } = await client.query<TaskRow>(
    `SELECT id, seq_no, mode, video_ref, source_name, title, poster_ref, replication_count, prompts_snapshot, settings_snapshot, status, created_at, (SELECT COALESCE(u.name, u.email) FROM users u WHERE u.id = tasks.created_by) AS author
     FROM tasks ORDER BY created_at DESC LIMIT 100`,
  );
  return rows.map((r) => toTask(r, false));
}


/**
 * Переименование исследования.
 *
 * Пустое название законно и означает «убрать своё» — заголовок вернётся к имени
 * файла. Поэтому `null` здесь не ошибка, а значение.
 *
 * Проверка принадлежности не нужна отдельным запросом: RLS уже ограничивает
 * `tasks` арендатором сессии, и `UPDATE` по чужому идентификатору не найдёт
 * строки. Дополнительный `SELECT` перед этим создавал бы окно между проверкой и
 * записью — и ложное ощущение, что защита именно в нём.
 */
/**
 * Задача по человеческому номеру.
 *
 * Пара (арендатор, номер) уникальна — уникальный индекс заведён миграцией 28, —
 * но условия на tenant_id здесь нет намеренно: его накладывает RLS. Дописать
 * его руками значило бы завести второй способ ограничить выборку, и однажды
 * один из них поправили бы, а другой нет.
 */
export async function getTaskBySeqNo(
  client: PoolClient,
  seqNo: number,
): Promise<LaunchedTask | null> {
  const { rows } = await client.query<TaskRow>(
    `SELECT id, seq_no, mode, video_ref, source_name, title, poster_ref, replication_count, prompts_snapshot, settings_snapshot, status, created_at, (SELECT COALESCE(u.name, u.email) FROM users u WHERE u.id = tasks.created_by) AS author
       FROM tasks WHERE seq_no = $1`,
    [seqNo],
  );
  return rows[0] ? toTask(rows[0], false) : null;
}


export async function renameTask(
  client: PoolClient,
  id: string,
  title: string | null,
): Promise<boolean> {
  const { rowCount } = await client.query(
    "UPDATE tasks SET title = $2 WHERE id = $1::uuid",
    [id, title],
  );
  return (rowCount ?? 0) > 0;
}
