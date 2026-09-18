-- ─────────────────────────────────────────────────────────────────────────
-- 56. Время последнего движения генерации набора персон
-- ─────────────────────────────────────────────────────────────────────────
--
-- `generated_count` теперь означает число строк в `personas`, а не число
-- обработанных моделью. Реаперу нужен отдельный момент движения: во время
-- обогащения строки ещё не записаны, но задача может быть живой.
--
-- Миграция только добавляет колонку и узкую обслуживающую политику. FORCE RLS
-- остаётся включённым: на managed PostgreSQL обход всех арендаторов требует
-- политики владельцу, а не SUPERUSER или BYPASSRLS.

BEGIN;

ALTER TABLE persona_sets
  ADD COLUMN IF NOT EXISTS progress_at timestamptz;

-- Для уже существующих строк начальной точкой считается создание набора.
UPDATE persona_sets
   SET progress_at = created_at
 WHERE progress_at IS NULL;

ALTER TABLE persona_sets
  ALTER COLUMN progress_at SET DEFAULT now(),
  ALTER COLUMN progress_at SET NOT NULL;

DO $$
DECLARE
  owner_role text;
BEGIN
  SELECT tableowner INTO owner_role
    FROM pg_tables
   WHERE schemaname = 'public' AND tablename = 'persona_sets';

  EXECUTE 'DROP POLICY IF EXISTS persona_sets_reaper_read ON persona_sets';
  EXECUTE format(
    'CREATE POLICY persona_sets_reaper_read ON persona_sets '
    'FOR SELECT TO %I USING (status = ''generating'')',
    owner_role
  );

  EXECUTE 'DROP POLICY IF EXISTS persona_sets_reaper_finish ON persona_sets';
  EXECUTE format(
    'CREATE POLICY persona_sets_reaper_finish ON persona_sets '
    'FOR UPDATE TO %I USING (status = ''generating'') WITH CHECK (true)',
    owner_role
  );
END $$;

COMMIT;
