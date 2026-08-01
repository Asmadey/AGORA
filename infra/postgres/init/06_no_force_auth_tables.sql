-- 06_no_force_auth_tables.sql
--
-- Снять FORCE RLS с teams и team_members (ENABLE остаётся).
--
-- Причина: SECURITY DEFINER функции (find_user_by_email, memberships_of_user,
-- membership_role) выполняются от имени gen_user — владельца таблиц. С FORCE
-- RLS владелец тоже подчиняется политикам, а app.current_tenant() в момент
-- логина возвращает NULL → функции отдают 0 строк → логин невозможен.
--
-- На managed PostgreSQL (TimeWeb) нельзя выдать BYPASSRLS — нет суперпользователя.
-- Единственный путь: снять FORCE с двух таблиц, оставив ENABLE. Это безопасно:
-- приложение подключается под agora_app (не владелец), и ENABLE RLS его изолирует.
-- gen_user обходит RLS только в SECURITY DEFINER функциях при логине.
--
-- Это исключение из правила «FORCE RLS не снимается». Причина — ограничение
-- managed-инстанса: BYPASSRLS недоступен без суперпользователя, а суперпользователя
-- нет. Если инстанс будет перенесён на self-managed PostgreSQL с BYPASSRLS —
-- этот файл нужно заменить на ALTER TABLE ... FORCE ROW LEVEL SECURITY.

ALTER TABLE teams NO FORCE ROW LEVEL SECURITY;
ALTER TABLE team_members NO FORCE ROW LEVEL SECURITY;

-- Верификация: ENABLE остаётся, FORCE снят.
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT relname, relrowsecurity, relforcerowsecurity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
      AND relname IN ('teams', 'team_members')
  LOOP
    ASSERT r.relrowsecurity, 'RLS должен быть ENABLE на %', r.relname;
    ASSERT NOT r.relforcerowsecurity, 'FORCE RLS должен быть снят на %', r.relname;
  END LOOP;
END $$;