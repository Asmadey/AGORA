-- ─────────────────────────────────────────────────────────────────────────
-- Задача #24 — История версий портретов аудитории.
--
-- Таблица audience_portraits хранит только текущее состояние. Для ручной
-- правки с версионированием (как в промпт-студии #26) нужна отдельная таблица
-- истории. Каждое сохранение пишет новую строку; текущее тело портрета
-- обновляется в audience_portraits, а старое сохраняется здесь.
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audience_portrait_versions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  portrait_id  uuid NOT NULL REFERENCES audience_portraits(id) ON DELETE CASCADE,
  version      integer NOT NULL DEFAULT 1 CHECK (version > 0),
  body_md      text NOT NULL DEFAULT '',
  editor       text NOT NULL DEFAULT 'manual',
  created_by   uuid,  -- user id, optional
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS portrait_versions_portrait_idx
  ON audience_portrait_versions (portrait_id);
CREATE INDEX IF NOT EXISTS portrait_versions_tenant_idx
  ON audience_portrait_versions (tenant_id);

-- Уникальность версии в рамках одного портрета
CREATE UNIQUE INDEX IF NOT EXISTS portrait_versions_portrait_version_uniq
  ON audience_portrait_versions (portrait_id, version);

-- RLS
ALTER TABLE audience_portrait_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audience_portrait_versions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audience_portrait_versions_tenant_isolation
  ON audience_portrait_versions;
CREATE POLICY audience_portrait_versions_tenant_isolation
  ON audience_portrait_versions
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

-- Grant — та же роль, что и для остальных таблиц
GRANT SELECT, INSERT, UPDATE, DELETE ON audience_portrait_versions TO agora_app;