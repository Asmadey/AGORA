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
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agora_app') THEN
    CREATE ROLE agora_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  ELSE
    -- Если роль уже была — приводим к безопасному состоянию принудительно.
    ALTER ROLE agora_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

-- Роль, под которой отдаётся публичная страница расшаренного отчёта (#29).
-- Прав ещё меньше: только чтение, и только то, что разрешит политика по токену.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agora_share') THEN
    CREATE ROLE agora_share NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  ELSE
    ALTER ROLE agora_share NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;


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
