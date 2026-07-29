-- AGORA · 01 · расширения, роль приложения, схема тенант-контекста
-- Задача #2 (Схемы БД + RLS). Идемпотентно: скрипт можно прогнать повторно.

-- pgcrypto: gen_random_uuid() для первичных ключей и digest() для хеширования
-- токенов публичных ссылок (#29 — токен хранится хешем, как пароль).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- citext: e-mail пользователя должен сравниваться без учёта регистра.
CREATE EXTENSION IF NOT EXISTS citext;


-- ─────────────────────────────────────────────────────────────────────────
-- Роль приложения
-- ─────────────────────────────────────────────────────────────────────────
-- Критично: RLS НЕ действует на суперпользователя и на роль с BYPASSRLS, а на
-- владельца таблицы не действует без FORCE. Поэтому приложение обязано ходить в
-- базу под отдельной ограниченной ролью, а не под postgres. Владелец таблиц —
-- миграционная роль; приложение получает только DML-права.
-- Существующая роль НЕ приводится к безопасному виду через ALTER: снятие
-- SUPERUSER и BYPASSRLS разрешено только суперпользователю, а на managed-инстансе
-- (TimeWeb, RDS и подобные) выданная роль им не является. Прежняя редакция
-- падала на `ALTER ROLE agora_app NOSUPERUSER …` даже тогда, когда роль уже была
-- в нужном состоянии. Поэтому здесь проверка вместо принуждения: небезопасная
-- роль останавливает миграцию с внятным текстом, безопасная — пропускается.
-- Это честнее: скрипт не делает вид, что починил то, чего починить не может.
CREATE OR REPLACE FUNCTION pg_temp.ensure_restricted_role(p_role text)
RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
  r record;
BEGIN
  SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
    INTO r FROM pg_roles WHERE rolname = p_role;

  IF NOT FOUND THEN
    EXECUTE format(
      'CREATE ROLE %I NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', p_role);
    RETURN;
  END IF;

  IF r.rolsuper OR r.rolbypassrls THEN
    RAISE EXCEPTION
      'роль % имеет SUPERUSER или BYPASSRLS: политики RLS на неё не действуют и изоляция арендаторов не работает. Снимите атрибуты от имени суперпользователя: ALTER ROLE % NOSUPERUSER NOBYPASSRLS',
      p_role, p_role;
  END IF;

  -- CREATEDB/CREATEROLE снимаются и без суперпользователя, но только владельцем
  -- роли. Если и это запрещено — предупреждение, а не остановка: на изоляцию
  -- арендаторов эти два атрибута не влияют.
  IF r.rolcreatedb OR r.rolcreaterole THEN
    BEGIN
      EXECUTE format('ALTER ROLE %I NOCREATEDB NOCREATEROLE', p_role);
    EXCEPTION WHEN insufficient_privilege THEN
      RAISE WARNING 'у роли % остались CREATEDB/CREATEROLE, снять их текущими правами нельзя', p_role;
    END;
  END IF;
END
$fn$;

SELECT pg_temp.ensure_restricted_role('agora_app');

-- Роль, под которой отдаётся публичная страница расшаренного отчёта (#29).
-- Прав ещё меньше: только чтение, и только то, что разрешит политика по токену.
SELECT pg_temp.ensure_restricted_role('agora_share');


-- ─────────────────────────────────────────────────────────────────────────
-- Тенант-контекст
-- ─────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS app;

-- Текущий арендатор берётся из параметра сессии app.tenant_id, который слой
-- доступа выставляет через SET LOCAL внутри транзакции.
--
-- Три тонкости, каждая из которых иначе становится дырой:
--   1. current_setting(..., true) — missing_ok. Без него незаданный контекст даёт
--      ошибку 42704 вместо пустой выборки, и приложение может её проглотить.
--   2. NULLIF(..., '') — пустая строка не приводится к uuid и роняет запрос;
--      нам нужен NULL, то есть «арендатор не задан».
--   3. Возврат NULL при незаданном контексте даёт default deny: сравнение
--      tenant_id = NULL истинным не бывает, поэтому не видно ни одной строки.
CREATE OR REPLACE FUNCTION app.current_tenant()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid;
$$;

-- Хеш токена публичной ссылки из параметра сессии app.share_token.
-- Сам токен в базе не хранится и в политику не попадает — только его SHA-256.
CREATE OR REPLACE FUNCTION app.current_share_token_hash()
RETURNS text
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
  SELECT CASE
    WHEN NULLIF(current_setting('app.share_token', true), '') IS NULL THEN NULL
    ELSE encode(digest(current_setting('app.share_token', true), 'sha256'), 'hex')
  END;
$$;

COMMENT ON FUNCTION app.current_tenant() IS
  'Арендатор текущей транзакции из SET LOCAL app.tenant_id. NULL = контекст не задан = не видно ничего.';
COMMENT ON FUNCTION app.current_share_token_hash() IS
  'SHA-256 токена публичной ссылки из SET LOCAL app.share_token. Единственный легальный путь в обход тенант-изоляции.';

GRANT USAGE ON SCHEMA app TO agora_app, agora_share;
GRANT USAGE ON SCHEMA public TO agora_app, agora_share;
