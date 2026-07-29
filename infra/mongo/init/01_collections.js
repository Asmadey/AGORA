// AGORA · MongoDB · коллекции, индексы, валидаторы (задача #2, PRD §10)
//
// В Mongo уезжает всё, что либо крупное, либо со свободной формой: разбор кадров,
// ответы персон, черновики визарда, grounding-датасет, разбор файлов контекста.
// Реляционная целостность и RLS остаются в Postgres.
//
// ВАЖНО: у Mongo нет RLS. Изоляция арендаторов здесь — обязанность слоя доступа,
// поэтому tenant_id объявлен required в КАЖДОЙ коллекции и входит первым полем
// в каждый индекс. Запрос без tenant_id обязан отсекаться в коде (agent_core.db).
//
// Идемпотентно: createCollection обёрнут проверкой, createIndex по своей природе
// повторяем.

const dbName = process.env.MONGO_INITDB_DATABASE || "agora";
const target = db.getSiblingDB(dbName);

function ensureCollection(name, validator) {
  const exists = target.getCollectionNames().indexOf(name) !== -1;
  if (!exists) {
    target.createCollection(name, validator ? { validator: validator } : {});
    print("создана коллекция: " + name);
  } else if (validator) {
    target.runCommand({ collMod: name, validator: validator });
    print("обновлён валидатор: " + name);
  }
}

const tenantRequired = {
  $jsonSchema: {
    bsonType: "object",
    required: ["tenant_id"],
    properties: {
      tenant_id: {
        bsonType: "string",
        description: "UUID арендатора. Обязателен: изоляцию в Mongo обеспечивает код.",
      },
    },
  },
};

// ── Разбор кадров: самый дорогой артефакт пайплайна, кэшируется (#16) ──────
ensureCollection("chunk_analyses", {
  $jsonSchema: {
    bsonType: "object",
    required: ["tenant_id", "task_id"],
    properties: {
      tenant_id: { bsonType: "string" },
      task_id: { bsonType: "string" },
      // Хеш содержимого панели кадров. По нему берётся кэш при перезапуске (#30):
      // тот же материал не разбирается VLM повторно.
      content_hash: { bsonType: "string" },
      segment_index: { bsonType: "int" },
      analysis: { bsonType: "object" },
    },
  },
});
target.chunk_analyses.createIndex({ tenant_id: 1, task_id: 1, segment_index: 1 });
target.chunk_analyses.createIndex({ content_hash: 1 }, { sparse: true });

// ── Ответы персон (#18): основной объём записи ────────────────────────────
ensureCollection("persona_answers", {
  $jsonSchema: {
    bsonType: "object",
    required: ["tenant_id", "task_id", "persona_id"],
    properties: {
      tenant_id: { bsonType: "string" },
      task_id: { bsonType: "string" },
      persona_id: { bsonType: "string" },
      // Номер повтора при «Перекрытии» (#11): 1..replication_count.
      replication: { bsonType: "int" },
      scores: { bsonType: "object" },
      verbatims: { bsonType: "object" },
      grounding_refs: { bsonType: "array" },
      qa_flags: { bsonType: "array" },
    },
  },
});
target.persona_answers.createIndex({ tenant_id: 1, task_id: 1, persona_id: 1, replication: 1 });
// Допрос персоны в чате (#28) читает её прежние ответы по конкретной задаче.
target.persona_answers.createIndex({ tenant_id: 1, persona_id: 1, task_id: 1 });

// ── Черновики визарда (#7) ────────────────────────────────────────────────
ensureCollection("wizard_drafts", tenantRequired);
target.wizard_drafts.createIndex({ tenant_id: 1, user_id: 1 });
// Черновики живут 30 дней и подчищаются самим Mongo.
target.wizard_drafts.createIndex({ updated_at: 1 }, { expireAfterSeconds: 60 * 60 * 24 * 30 });

// ── Grounding-датасет (#23): 165 карточек респондентов ────────────────────
// tenant_id здесь тоже обязателен: у арендатора может быть свой корпус.
ensureCollection("grounding_dataset", tenantRequired);
target.grounding_dataset.createIndex({ tenant_id: 1, respondent_id: 1 }, { unique: true, sparse: true });
target.grounding_dataset.createIndex({
  tenant_id: 1,
  "socio_demographics.age_group": 1,
  "socio_demographics.geo": 1,
  "socio_demographics.gender": 1,
});

// ── Разбор файлов контекста аудитории (#31) ───────────────────────────────
ensureCollection("audience_context_files", tenantRequired);
target.audience_context_files.createIndex({ tenant_id: 1, file_id: 1 });

print("MongoDB готова: " + target.getCollectionNames().join(", "));
