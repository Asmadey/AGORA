-- AGORA · 03 · Row Level Security
-- Задача #2, метрика rls_tenant. Идемпотентно: политики пересоздаются через
-- DROP POLICY IF EXISTS.
--
-- Три правила, без которых RLS создаёт ложное чувство защиты:
--   1. ENABLE недостаточно — владелец таблицы обходит политики. Нужен FORCE.
--   2. Суперпользователь и роль с BYPASSRLS игнорируют политики всегда.
--      Приложение ходит под agora_app (NOSUPERUSER NOBYPASSRLS) — см. 01.
--   3. Незаданный тенант-контекст обязан давать пустую выборку, а не всю таблицу.
--      app.current_tenant() возвращает NULL, сравнение с NULL не истинно → default deny.

-- ─────────────────────────────────────────────────────────────────────────
-- Включение RLS
-- ─────────────────────────────────────────────────────────────────────────
ALTER TABLE teams                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams                  FORCE ROW LEVEL SECURITY;
ALTER TABLE team_members           ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_members           FORCE ROW LEVEL SECURITY;
ALTER TABLE settings               ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings               FORCE ROW LEVEL SECURITY;
ALTER TABLE projects               ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects               FORCE ROW LEVEL SECURITY;
ALTER TABLE persona_sets           ENABLE ROW LEVEL SECURITY;
ALTER TABLE persona_sets           FORCE ROW LEVEL SECURITY;
ALTER TABLE personas               ENABLE ROW LEVEL SECURITY;
ALTER TABLE personas               FORCE ROW LEVEL SECURITY;
ALTER TABLE audience_portraits     ENABLE ROW LEVEL SECURITY;
ALTER TABLE audience_portraits     FORCE ROW LEVEL SECURITY;
ALTER TABLE audience_context_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE audience_context_files FORCE ROW LEVEL SECURITY;
ALTER TABLE prompts                ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompts                FORCE ROW LEVEL SECURITY;
ALTER TABLE surveys                ENABLE ROW LEVEL SECURITY;
ALTER TABLE surveys                FORCE ROW LEVEL SECURITY;
ALTER TABLE tasks                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks                  FORCE ROW LEVEL SECURITY;
ALTER TABLE reports                ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports                FORCE ROW LEVEL SECURITY;
ALTER TABLE report_shares          ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_shares          FORCE ROW LEVEL SECURITY;
ALTER TABLE report_share_views     ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_share_views     FORCE ROW LEVEL SECURITY;
ALTER TABLE chat_threads           ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_threads           FORCE ROW LEVEL SECURITY;
ALTER TABLE chat_messages          ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages          FORCE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────────────────
-- Арендатор и членство
-- ─────────────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS teams_tenant_isolation ON teams;
CREATE POLICY teams_tenant_isolation ON teams
  FOR ALL TO agora_app
  USING (id = app.current_tenant())
  WITH CHECK (id = app.current_tenant());

DROP POLICY IF EXISTS team_members_tenant_isolation ON team_members;
CREATE POLICY team_members_tenant_isolation ON team_members
  FOR ALL TO agora_app
  USING (team_id = app.current_tenant())
  WITH CHECK (team_id = app.current_tenant());

-- ─────────────────────────────────────────────────────────────────────────
-- Прикладные таблицы: единообразная изоляция по tenant_id
-- ─────────────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS settings_tenant_isolation ON settings;
CREATE POLICY settings_tenant_isolation ON settings
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS projects_tenant_isolation ON projects;
CREATE POLICY projects_tenant_isolation ON projects
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS persona_sets_tenant_isolation ON persona_sets;
CREATE POLICY persona_sets_tenant_isolation ON persona_sets
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS personas_tenant_isolation ON personas;
CREATE POLICY personas_tenant_isolation ON personas
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS audience_portraits_tenant_isolation ON audience_portraits;
CREATE POLICY audience_portraits_tenant_isolation ON audience_portraits
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS audience_context_files_tenant_isolation ON audience_context_files;
CREATE POLICY audience_context_files_tenant_isolation ON audience_context_files
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS surveys_tenant_isolation ON surveys;
CREATE POLICY surveys_tenant_isolation ON surveys
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS tasks_tenant_isolation ON tasks;
CREATE POLICY tasks_tenant_isolation ON tasks
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS report_share_views_tenant_isolation ON report_share_views;
CREATE POLICY report_share_views_tenant_isolation ON report_share_views
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS chat_threads_tenant_isolation ON chat_threads;
CREATE POLICY chat_threads_tenant_isolation ON chat_threads
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS chat_messages_tenant_isolation ON chat_messages;
CREATE POLICY chat_messages_tenant_isolation ON chat_messages
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS report_shares_tenant_isolation ON report_shares;
CREATE POLICY report_shares_tenant_isolation ON report_shares
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

-- ─────────────────────────────────────────────────────────────────────────
-- Промпты: читаем свои + дефолтные, правим только свои
-- ─────────────────────────────────────────────────────────────────────────
-- Резолв «активная версия арендатора → дефолт» требует видеть чужие по формальному
-- признаку строки (tenant_id IS NULL). Поэтому чтение и запись разведены: иначе
-- арендатор смог бы отредактировать seed-промпт и сломать его всем остальным.
DROP POLICY IF EXISTS prompts_read_own_and_defaults ON prompts;
CREATE POLICY prompts_read_own_and_defaults ON prompts
  FOR SELECT TO agora_app
  USING (tenant_id = app.current_tenant() OR tenant_id IS NULL);

DROP POLICY IF EXISTS prompts_write_own_only ON prompts;
CREATE POLICY prompts_write_own_only ON prompts
  FOR INSERT TO agora_app
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS prompts_update_own_only ON prompts;
CREATE POLICY prompts_update_own_only ON prompts
  FOR UPDATE TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS prompts_delete_own_only ON prompts;
CREATE POLICY prompts_delete_own_only ON prompts
  FOR DELETE TO agora_app
  USING (tenant_id = app.current_tenant());

-- ─────────────────────────────────────────────────────────────────────────
-- Отчёты: свои + доступ по токену публичной ссылки
-- ─────────────────────────────────────────────────────────────────────────
-- Единственный санкционированный обход тенант-изоляции во всей системе (#29).
-- Условия жизни ссылки (не отозвана, не истекла) проверяются ЗДЕСЬ, в политике,
-- а не в коде приложения: код можно забыть обновить, политику обойти нельзя.
DROP POLICY IF EXISTS reports_tenant_isolation ON reports;
CREATE POLICY reports_tenant_isolation ON reports
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS reports_public_share_read ON reports;
CREATE POLICY reports_public_share_read ON reports
  FOR SELECT TO agora_share
  USING (
    EXISTS (
      SELECT 1
      FROM report_shares s
      WHERE s.report_id = reports.id
        AND s.token_hash = app.current_share_token_hash()
        AND s.revoked_at IS NULL
        AND (s.expires_at IS NULL OR s.expires_at > now())
    )
  );

-- Публичной странице нужно прочитать саму запись ссылки, чтобы узнать scope
-- ('full' или 'aggregate'). Те же условия жизни.
DROP POLICY IF EXISTS report_shares_public_read ON report_shares;
CREATE POLICY report_shares_public_read ON report_shares
  FOR SELECT TO agora_share
  USING (
    token_hash = app.current_share_token_hash()
    AND revoked_at IS NULL
    AND (expires_at IS NULL OR expires_at > now())
  );

-- Просмотр публичной страницы обязан попасть в аудит-лог, поэтому agora_share
-- может ТОЛЬКО вставлять строку просмотра — и только для живой ссылки.
DROP POLICY IF EXISTS report_share_views_public_insert ON report_share_views;
CREATE POLICY report_share_views_public_insert ON report_share_views
  FOR INSERT TO agora_share
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM report_shares s
      WHERE s.id = report_share_views.share_id
        AND s.token_hash = app.current_share_token_hash()
        AND s.revoked_at IS NULL
        AND (s.expires_at IS NULL OR s.expires_at > now())
    )
  );

-- ─────────────────────────────────────────────────────────────────────────
-- Права
-- ─────────────────────────────────────────────────────────────────────────
-- users — глобальная таблица идентичности, RLS на ней нет; ограничивается
-- прикладным кодом и Auth.js (задача #3).
GRANT SELECT, INSERT, UPDATE ON users TO agora_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON
  teams, team_members, settings, projects, persona_sets, personas,
  audience_portraits, audience_context_files, prompts, surveys, tasks,
  reports, report_shares, report_share_views, chat_threads, chat_messages
TO agora_app;

-- Публичная роль: только чтение отчёта и его ссылки + запись в аудит.
GRANT SELECT ON reports, report_shares TO agora_share;
GRANT INSERT ON report_share_views TO agora_share;

-- Никаких прав на будущие таблицы по умолчанию — только осознанный GRANT.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
