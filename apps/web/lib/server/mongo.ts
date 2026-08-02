import "server-only";
import { MongoClient, type Db, type Collection } from "mongodb";

/**
 * Единственный модуль доступа к MongoDB (задача #7).
 *
 * У MongoDB нет RLS — изоляция арендаторов держится только на фильтре tenant_id
 * в каждом запросе. Поэтому:
 *   1. tenant_id берётся из сессии, а не из аргументов функции
 *   2. Ни одна экспортируемая функция не принимает tenantId параметром
 *   3. Каждый запрос к wizard_drafts включает фильтр по tenant_id
 *
 * Нарушение любого из этих правил означает чужие данные.
 */

// Имена переменных — MONGODB_URL и MONGO_DB: именно так они заданы в .env.local,
// в .env.example, в обоих сервисах docker-compose.yml и в agent_core/config.py.
// Прежняя редакция читала MONGODB_URI и MONGODB_DB, которых не существует нигде,
// а восклицательный знак глушил проверку типов — падение случилось бы в рантайме
// на разборе URI, далеко от причины.
const MONGODB_URL = process.env.MONGODB_URL;
const DB_NAME = process.env.MONGO_DB || "agora";

let client: MongoClient | null = null;
let db: Db | null = null;

async function getDb(): Promise<Db> {
  if (!client) {
    if (!MONGODB_URL) {
      throw new Error("MONGODB_URL не задан: черновики визарда не могут работать без MongoDB");
    }
    client = new MongoClient(MONGODB_URL);
    await client.connect();
  }
  if (!db) {
    db = client.db(DB_NAME);
  }
  return db;
}

/** Сессия пользователя — tenant_id берётся отсюда, не из аргументов. */
export interface SessionUser {
  userId: string;
  tenantId: string;
}

async function getDraftsCollection(): Promise<Collection> {
  const database = await getDb();
  return database.collection("wizard_drafts");
}

/** Загрузить черновик визарда для проекта. tenant_id — из сессии. */
export async function loadDraft(session: SessionUser, projectId: string) {
  const coll = await getDraftsCollection();
  const doc = await coll.findOne(
    { tenant_id: session.tenantId, project_id: projectId },
    { projection: { _id: 0, tenant_id: 0 } },
  );
  return doc;
}

/** Сохранить черновик. tenant_id — из сессии, не из данных. */
export async function saveDraft(
  session: SessionUser,
  projectId: string,
  data: Record<string, unknown>,
) {
  const coll = await getDraftsCollection();
  await coll.updateOne(
    { tenant_id: session.tenantId, project_id: projectId },
    {
      $set: {
        tenant_id: session.tenantId,
        project_id: projectId,
        user_id: session.userId,
        data,
        updated_at: new Date(),
      },
    },
    { upsert: true },
  );
}

/** Удалить черновик. tenant_id — из сессии. */
export async function deleteDraft(
  session: SessionUser,
  projectId: string,
) {
  const coll = await getDraftsCollection();
  await coll.deleteOne({
    tenant_id: session.tenantId,
    project_id: projectId,
  });
}