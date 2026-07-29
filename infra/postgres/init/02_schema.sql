-- AGORA · 02 · таблицы (PRD §10 + фичи ревизии §20)
-- Задача #2. Идемпотентно: все CREATE TABLE — IF NOT EXISTS.
--
-- Модель арендатора (Decision Log #9): «команда = арендатор». teams.id И ЕСТЬ
-- tenant_id; во всех прикладных таблицах он вынесен отдельной колонкой, чтобы
-- политика RLS не ходила по джойнам.

-- ─────────────────────────────────────────────────────────────────────────
-- Идентичность и арендаторы
-- ─────────────────────────────────────────────────────────────────────────

-- Пользователь — глобальная сущность: один человек может состоять в нескольких
-- командах. Форма полей совместима с адаптером Auth.js, чтобы задача #3 только
-- добавила accounts/sessions, а не переделывала users.
CREATE TABLE IF NOT EXISTS users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          citext UNIQUE NOT NULL,
  name           text,
  email_verified timestamptz,
  image          text,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS teams (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE teams IS 'Арендатор. teams.id используется как tenant_id во всех прикладных таблицах.';

CREATE TABLE IF NOT EXISTS team_members (
  team_id   uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id   uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role      text NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'member')),
  joined_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (team_id, user_id)
);

-- ─────────────────────────────────────────────────────────────────────────
-- Настройки арендатора (#27)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS settings (
  tenant_id                 uuid PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
  -- NULL = «авто», то есть без жёсткого потолка (дефолт по Decision Log #5).
  cost_cap_calls            integer CHECK (cost_cap_calls IS NULL OR cost_cap_calls > 0),
  whisper_model             text NOT NULL DEFAULT 'large-v3'
                            CHECK (whisper_model IN ('large-v3', 'large-v3-turbo')),
  default_replication_count integer NOT NULL DEFAULT 1
                            CHECK (default_replication_count BETWEEN 1 AND 10),
  provider_config           jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at                timestamptz NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────
-- Проекты, персоны, знания
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name       text NOT NULL,
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS persona_sets (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name              text NOT NULL,
  size              integer NOT NULL CHECK (size > 0),
  -- Критерии генерации целиком: пол/возраст/гео/образование + seed.
  -- Хранятся ради воспроизводимости и ради эталонного (reference) прогона
  -- persona_grounding — см. PRD §13.
  generation_config jsonb NOT NULL DEFAULT '{}'::jsonb,
  seed              bigint,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS personas (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  persona_set_id uuid REFERENCES persona_sets(id) ON DELETE CASCADE,
  name           text NOT NULL,
  -- Вся Persona DNA: 8 категорий, 40–60 полей MVP. Валидируется canonical
  -- JSON Schema из packages/shared (задача #4), а не структурой таблицы —
  -- иначе каждое расширение DNA превращалось бы в миграцию.
  dna            jsonb NOT NULL,
  narrative      text,
  seed           bigint,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audience_portraits (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name       text NOT NULL,
  body_md    text NOT NULL DEFAULT '',
  -- 'manual' — написан руками, 'distilled' — авто-дистилляция из датасета (#24),
  -- 'context_file' — получен из файла, приложенного пользователем (#31).
  source     text NOT NULL DEFAULT 'manual'
             CHECK (source IN ('manual', 'distilled', 'context_file')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Метаданные файла доп. контекста (#31); сам файл — в S3, разбор — в MongoDB.
CREATE TABLE IF NOT EXISTS audience_context_files (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  portrait_id  uuid REFERENCES audience_portraits(id) ON DELETE SET NULL,
  filename     text NOT NULL,
  content_type text,
  size_bytes   bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
  s3_key       text NOT NULL,
  status       text NOT NULL DEFAULT 'uploaded'
               CHECK (status IN ('uploaded', 'distilled', 'failed')),
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────
-- Промпт-студия (#26)
-- ─────────────────────────────────────────────────────────────────────────
-- tenant_id NULL = дефолтная (seed) версия, общая для всех арендаторов.
-- Резолв: активная версия арендатора → дефолт. Политики ниже разрешают всем
-- ЧИТАТЬ дефолты, но ПРАВИТЬ — только свои строки.
CREATE TABLE IF NOT EXISTS prompts (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid REFERENCES teams(id) ON DELETE CASCADE,
  key          text NOT NULL,
  stage        text NOT NULL,
  template     text NOT NULL,
  variables    jsonb NOT NULL DEFAULT '[]'::jsonb,
  model_params jsonb NOT NULL DEFAULT '{}'::jsonb,
  version      integer NOT NULL DEFAULT 1 CHECK (version > 0),
  is_active    boolean NOT NULL DEFAULT false,
  is_default   boolean NOT NULL DEFAULT false,
  created_at   timestamptz NOT NULL DEFAULT now(),
  -- Дефолт у ключа ровно один и он ничей.
  CONSTRAINT prompts_default_has_no_tenant CHECK (NOT is_default OR tenant_id IS NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS prompts_default_key_uniq
  ON prompts (key) WHERE is_default;
CREATE UNIQUE INDEX IF NOT EXISTS prompts_tenant_key_version_uniq
  ON prompts (tenant_id, key, version) WHERE tenant_id IS NOT NULL;
-- Активная версия ключа у арендатора тоже ровно одна.
CREATE UNIQUE INDEX IF NOT EXISTS prompts_tenant_key_active_uniq
  ON prompts (tenant_id, key) WHERE is_active AND tenant_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────
-- Анкеты и прогоны
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS surveys (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name       text NOT NULL,
  questions  jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  project_id        uuid REFERENCES projects(id) ON DELETE CASCADE,
  persona_set_id    uuid REFERENCES persona_sets(id) ON DELETE SET NULL,
  survey_id         uuid REFERENCES surveys(id) ON DELETE SET NULL,
  mode              text NOT NULL DEFAULT 'short' CHECK (mode IN ('short', 'long')),
  video_ref         text,
  audio_ref         text,
  -- «Перекрытие» (#11): сколько раз каждая персона проходит анкету.
  replication_count integer NOT NULL DEFAULT 1 CHECK (replication_count BETWEEN 1 AND 10),
  -- Пиннинг версий промптов на прогон — без него результат невоспроизводим,
  -- потому что промпты правятся в Промпт-студии между прогонами.
  prompts_snapshot  jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- Перезапуск с той же аудиторией (#30).
  parent_task_id    uuid REFERENCES tasks(id) ON DELETE SET NULL,
  -- true = «допрос» (персона помнит первый прогон), false = «чистый прогон».
  carry_over_memory boolean NOT NULL DEFAULT false,
  status            text NOT NULL DEFAULT 'QUEUED'
                    CHECK (status IN ('QUEUED', 'RUNNING', 'REPORT_READY', 'FAILED')),
  progress          jsonb NOT NULL DEFAULT '{}'::jsonb,
  error             text,
  created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  finished_at       timestamptz,
  -- Перезапуск обязан оставаться внутри своего арендатора.
  CONSTRAINT tasks_parent_not_self CHECK (parent_task_id IS NULL OR parent_task_id <> id)
);

CREATE TABLE IF NOT EXISTS reports (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  task_id         uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  aggregate       jsonb NOT NULL DEFAULT '{}'::jsonb,
  group_synthesis jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- Доверительные границы заполняются только при replication_count > 1.
  confidence      jsonb NOT NULL DEFAULT '{}'::jsonb,
  narrative       text,
  qa_flags        jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT reports_task_uniq UNIQUE (task_id)
);

-- ─────────────────────────────────────────────────────────────────────────
-- Публичные ссылки на отчёт (#29)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS report_shares (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  report_id  uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  -- Сам токен не хранится: только SHA-256. Утечка дампа базы не даёт доступа.
  token_hash text NOT NULL UNIQUE,
  -- 'full' — агрегат и поимённые персоны; 'aggregate' — только сводные метрики.
  scope      text NOT NULL DEFAULT 'full' CHECK (scope IN ('full', 'aggregate')),
  expires_at timestamptz,
  revoked_at timestamptz,
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report_share_views (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  share_id   uuid NOT NULL REFERENCES report_shares(id) ON DELETE CASCADE,
  viewed_at  timestamptz NOT NULL DEFAULT now(),
  -- IP хранится хешем: аудит нужен, персональные данные — нет.
  ip_hash    text,
  user_agent text
);

-- ─────────────────────────────────────────────────────────────────────────
-- Чат по результатам (#28)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_threads (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  task_id    uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  mode       text NOT NULL CHECK (mode IN ('analyst', 'persona')),
  -- Заполнен только в режиме допроса персоны.
  persona_id uuid REFERENCES personas(id) ON DELETE CASCADE,
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chat_threads_persona_mode CHECK (
    (mode = 'persona' AND persona_id IS NOT NULL) OR
    (mode = 'analyst' AND persona_id IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  thread_id  uuid NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
  role       text NOT NULL CHECK (role IN ('user', 'assistant')),
  content    text NOT NULL,
  -- Ссылки на таймкоды и цитаты: ответ без опоры на артефакты недопустим.
  citations  jsonb NOT NULL DEFAULT '[]'::jsonb,
  flags      jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────
-- Индексы: первым столбцом tenant_id, потому что каждый запрос идёт под RLS
-- и всегда фильтруется по арендатору.
-- ─────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS projects_tenant_idx           ON projects (tenant_id);
CREATE INDEX IF NOT EXISTS persona_sets_tenant_idx       ON persona_sets (tenant_id);
CREATE INDEX IF NOT EXISTS personas_tenant_set_idx       ON personas (tenant_id, persona_set_id);
CREATE INDEX IF NOT EXISTS portraits_tenant_idx          ON audience_portraits (tenant_id);
CREATE INDEX IF NOT EXISTS context_files_tenant_idx      ON audience_context_files (tenant_id);
CREATE INDEX IF NOT EXISTS prompts_key_idx               ON prompts (key);
CREATE INDEX IF NOT EXISTS surveys_tenant_idx            ON surveys (tenant_id);
CREATE INDEX IF NOT EXISTS tasks_tenant_created_idx      ON tasks (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS tasks_tenant_status_idx       ON tasks (tenant_id, status);
CREATE INDEX IF NOT EXISTS tasks_parent_idx              ON tasks (parent_task_id) WHERE parent_task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS reports_tenant_idx            ON reports (tenant_id);
CREATE INDEX IF NOT EXISTS shares_report_idx             ON report_shares (report_id);
CREATE INDEX IF NOT EXISTS share_views_share_idx         ON report_share_views (share_id, viewed_at DESC);
CREATE INDEX IF NOT EXISTS chat_threads_tenant_task_idx  ON chat_threads (tenant_id, task_id);
CREATE INDEX IF NOT EXISTS chat_messages_thread_idx      ON chat_messages (thread_id, created_at);
-- Поиск по DNA: карточка и сегментные срезы ходят внутрь jsonb.
CREATE INDEX IF NOT EXISTS personas_dna_gin_idx          ON personas USING gin (dna jsonb_path_ops);
