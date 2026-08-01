-- 06_owner_read_auth_tables.sql
--
-- FORCE RLS остаётся на teams и team_members. Вместо снятия FORCE
-- владельцу таблиц выдаётся явная политика SELECT — узкая и проверяемая.
--
-- Контекст: SECURITY DEFINER функции (find_user_by_email,
-- memberships_of_user, membership_role) читают teams и team_members
-- при логине, когда tenant_id ещё не установлен. С FORCE RLS владелец
-- тоже подчиняется политикам, а существующие политики привязаны к
-- agora_app — для владельца подходящей политики нет, значит 0 строк.
--
-- Решение: политика FOR SELECT TO <owner> USING (true) на двух таблицах.
-- Разница с NO FORCE: там владелец получал полный доступ ко всем командам
-- и ко всем таблицам; здесь — только SELECT, только на двух таблицах,
-- и это записано политикой, которую видно в pg_policies.
--
-- Роль владельца определяется динамически (current_user) — работает и на
-- managed-инстансе (gen_user), и на локальном Docker (agora).

-- FORCE RLS должен быть включён (03_rls.sql уже ставит, но проверим).
ALTER TABLE teams                FORCE ROW LEVEL SECURITY;
ALTER TABLE team_members          FORCE ROW LEVEL SECURITY;

-- Политика для владельца: SELECT только, только на этих таблицах.
-- Идемпотентна: DROP IF EXISTS + CREATE.
DROP POLICY IF EXISTS teams_definer_read ON teams;
DROP POLICY IF EXISTS team_members_definer_read ON team_members;

DO $$
DECLARE
  owner_role text := current_user;
BEGIN
  EXECUTE format(
    'CREATE POLICY teams_definer_read ON teams FOR SELECT TO %I USING (true)',
    owner_role
  );
  EXECUTE format(
    'CREATE POLICY team_members_definer_read ON team_members FOR SELECT TO %I USING (true)',
    owner_role
  );
END $$;

-- Верификация: FORCE на месте, политики созданы.
DO $$
DECLARE
  r RECORD;
  pol_count int;
BEGIN
  FOR r IN
    SELECT relname, relforcerowsecurity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
      AND relname IN ('teams', 'team_members')
  LOOP
    ASSERT r.relforcerowsecurity, 'FORCE RLS должен быть включён на %', r.relname;
  END LOOP;

  SELECT count(*) INTO pol_count
  FROM pg_policies
  WHERE schemaname = 'public'
    AND policyname IN ('teams_definer_read', 'team_members_definer_read');

  ASSERT pol_count = 2, 'ожидается 2 политики definer_read, найдено %', pol_count;
END $$;