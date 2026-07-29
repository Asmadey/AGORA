-- AGORA · 05 · аутентификация и членство (задача #3)
--
-- Модель — «команда = арендатор» (Decision Log #9). Таблицы users / teams /
-- team_members заведены миграцией 02; здесь добавляется только то, без чего
-- невозможен вход: хеш пароля и два узких способа прочитать идентичность ДО
-- того, как арендатор известен.
--
-- ─── Почему нужны SECURITY DEFINER ───────────────────────────────────────
-- Порядок при входе обратный обычному: сначала пользователь, потом арендатор.
-- Но team_members закрыт политикой `team_id = app.current_tenant()`, а на момент
-- проверки пароля контекст ещё пуст — политика честно вернёт ноль строк, и вход
-- станет невозможен в принципе.
--
-- Соблазнительный выход — снять RLS с team_members или дать приложению BYPASSRLS.
-- Оба открывают изоляцию целиком ради одного запроса. Вместо этого — две функции
-- с фиксированной сигнатурой: они выполняются с правами владельца, но отдают
-- ровно те строки, что относятся к одному переданному пользователю, и ничего
-- больше. Всё остальное приложение продолжает ходить через политики.
--
-- SET search_path обязателен: без него функция исполняется по пути вызывающего,
-- и вызывающий может подсунуть свою таблицу users во временной схеме.

-- ─────────────────────────────────────────────────────────────────────────
-- Хеш пароля
-- ─────────────────────────────────────────────────────────────────────────
-- Хранится строка формата PHC ($argon2id$v=19$m=…,t=…,p=…$salt$hash) — параметры
-- едут вместе с хешем, поэтому их можно поднять, не ломая старые записи.
-- NULL допустим: пользователь может быть заведён приглашением и ещё не задать пароль.
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text;

COMMENT ON COLUMN users.password_hash IS
  'argon2id в формате PHC. NULL = пароль не задан, вход по паролю запрещён.';

-- ─────────────────────────────────────────────────────────────────────────
-- Функции идентичности
-- ─────────────────────────────────────────────────────────────────────────

-- Поиск пользователя по адресу. Возвращает хеш — это осознанно: сравнение
-- выполняется в приложении, потому что проверка argon2 в базе означала бы
-- расширение pgcrypto с чужими параметрами и пароль в тексте запроса.
CREATE OR REPLACE FUNCTION app.find_user_by_email(p_email text)
RETURNS TABLE (id uuid, email text, name text, password_hash text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT u.id, u.email::text, u.name, u.password_hash
  FROM users u
  WHERE u.email = p_email::citext
  LIMIT 1;
$$;

COMMENT ON FUNCTION app.find_user_by_email(text) IS
  'Вход: адрес. Выход: одна строка пользователя вместе с хешем пароля. Обход RLS ограничен этим контрактом.';

-- Команды пользователя. Именно отсюда берётся tenant_id для сессии: список
-- арендаторов, в которые человек реально входит, и его роль в каждом.
CREATE OR REPLACE FUNCTION app.memberships_of_user(p_user_id uuid)
RETURNS TABLE (team_id uuid, team_name text, role text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT t.id, t.name, m.role
  FROM team_members m
  JOIN teams t ON t.id = m.team_id
  WHERE m.user_id = p_user_id
  ORDER BY m.joined_at;
$$;

COMMENT ON FUNCTION app.memberships_of_user(uuid) IS
  'Команды и роли одного пользователя. Единственный путь узнать арендатора до установки тенант-контекста.';

-- Проверка принадлежности. Нужна на каждом запросе: tenant_id приезжает из
-- подписанного токена, но подпись говорит лишь о том, что значение выдали мы, —
-- а членство могли отозвать после выдачи.
CREATE OR REPLACE FUNCTION app.membership_role(p_user_id uuid, p_team_id uuid)
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT m.role
  FROM team_members m
  WHERE m.user_id = p_user_id AND m.team_id = p_team_id;
$$;

COMMENT ON FUNCTION app.membership_role(uuid, uuid) IS
  'Актуальная роль пользователя в команде или NULL. Проверяет, что членство не отозвано после выдачи токена.';

-- ─────────────────────────────────────────────────────────────────────────
-- Права
-- ─────────────────────────────────────────────────────────────────────────
-- Сначала отбираем у PUBLIC: по умолчанию EXECUTE выдан всем, и без REVOKE
-- функция с правами владельца оказалась бы доступна любой роли, включая
-- agora_share, которая обслуживает публичные ссылки на отчёты.
REVOKE EXECUTE ON FUNCTION app.find_user_by_email(text)      FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION app.memberships_of_user(uuid)     FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION app.membership_role(uuid, uuid)   FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.find_user_by_email(text)    TO agora_app;
GRANT EXECUTE ON FUNCTION app.memberships_of_user(uuid)   TO agora_app;
GRANT EXECUTE ON FUNCTION app.membership_role(uuid, uuid) TO agora_app;

-- users не входит в список таблиц с RLS (миграция 03): пользователь — глобальная
-- сущность, один человек состоит в нескольких командах, и политика по tenant_id
-- к нему неприменима. Доступ ограничивается правами на колонки.
GRANT SELECT (id, email, name, image, email_verified) ON users TO agora_app;
GRANT UPDATE (name, image, password_hash) ON users TO agora_app;
