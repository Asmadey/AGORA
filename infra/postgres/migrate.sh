#!/usr/bin/env bash
# AGORA · миграции на ВНЕШНИЙ (managed) PostgreSQL
# Задача #2. Запускать с машины, у которой есть доступ к инстансу:
#
#   set -a; source .env.local; set +a
#   bash infra/postgres/migrate.sh
#
# ─── Зачем отдельный скрипт ──────────────────────────────────────────────
# Файлы 01–03 в init/ рассчитаны на docker-entrypoint-initdb.d, а он выполняется
# ровно один раз — при инициализации пустого каталога данных. На managed-инстансе
# каталог уже инициализирован провайдером, энтрипойнт не наш, и скрипты не
# выполнятся никогда. Молча: compose поднимется, приложение стартует, а таблиц
# не будет.
#
# 04_login_role.sh здесь тоже не годится — он вызывает psql под POSTGRES_USER
# без пароля, полагаясь на trust-аутентификацию внутри контейнера.
#
# ─── Про права ───────────────────────────────────────────────────────────
# gen_user на TimeWeb НЕ суперпользователь. Часть операций ему может быть
# недоступна, поэтому скрипт сначала проверяет права и печатает, чего не
# хватает, а не падает на середине с полуприменённой схемой.
set -euo pipefail

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; OFF=$'\033[0m'
ok()   { echo "${GRN}  OK${OFF}  $*"; }
warn() { echo "${YEL}WARN${OFF}  $*"; }
die()  { echo "${RED}FAIL${OFF}  $*" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT="$HERE/init"

: "${POSTGRES_ADMIN_URL:?POSTGRES_ADMIN_URL не задан — см. .env.local}"
: "${AGORA_APP_PASSWORD:?AGORA_APP_PASSWORD не задан}"
: "${AGORA_SHARE_PASSWORD:?AGORA_SHARE_PASSWORD не задан}"

case "$AGORA_APP_PASSWORD" in CHANGE_ME*) die "AGORA_APP_PASSWORD не заменён. openssl rand -base64 24";; esac
case "$AGORA_SHARE_PASSWORD" in CHANGE_ME*) die "AGORA_SHARE_PASSWORD не заменён. openssl rand -base64 24";; esac

command -v psql >/dev/null || die "psql не найден. macOS: brew install libpq && brew link --force libpq"

PSQL=(psql "$POSTGRES_ADMIN_URL" -v ON_ERROR_STOP=1 -X -q)
q() { psql "$POSTGRES_ADMIN_URL" -X -q -t -A -c "$1"; }

echo "── Подключение ──────────────────────────────────────────────────────"
q "SELECT 1" >/dev/null || die "не удалось подключиться. Проверьте PGSSLROOTCERT и доступ по IP из панели TimeWeb"
ok "$(q "SELECT version()" | cut -c1-60)"
ok "база: $(q 'SELECT current_database()')  роль: $(q 'SELECT current_user')"

echo
echo "── Права роли ───────────────────────────────────────────────────────"
IS_SUPER=$(q "SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
CAN_ROLE=$(q "SELECT rolcreaterole FROM pg_roles WHERE rolname = current_user")
IS_OWNER=$(q "SELECT pg_catalog.pg_get_userbyid(datdba) = current_user FROM pg_database WHERE datname = current_database()")

[ "$IS_SUPER" = "t" ] && warn "роль суперпользователь — RLS её не ограничивает; для проверки изоляции это важно" \
                      || ok "роль не суперпользователь (правильно: RLS обходится суперпользователем)"
[ "$IS_OWNER" = "t" ] && ok "роль владеет базой" || warn "роль НЕ владелец базы — часть DDL может быть запрещена"

if [ "$CAN_ROLE" != "t" ] && [ "$IS_SUPER" != "t" ]; then
  die "у роли нет CREATEROLE.

Политики RLS в 03_rls.sql выданы конкретным ролям (TO agora_app), поэтому без
права создавать роли схему применить нельзя. Варианты:
  1) выдать gen_user право CREATEROLE через панель TimeWeb или тикет в поддержку;
  2) попросить провайдера создать роли agora_app, agora_share, agora_login,
     agora_share_login заранее — дальше скрипт только выдаст им гранты."
fi
ok "CREATEROLE есть"

echo
echo "── Расширения ───────────────────────────────────────────────────────"
# pgcrypto и citext помечены trusted начиная с PostgreSQL 13 — владелец базы
# может создать их без суперпользователя. Если провайдер это запретил, узнаем
# сейчас, а не на середине 02_schema.sql.
for ext in pgcrypto citext; do
  if q "SELECT 1 FROM pg_extension WHERE extname = '$ext'" | grep -q 1; then
    ok "$ext уже установлено"
  else
    "${PSQL[@]}" -c "CREATE EXTENSION IF NOT EXISTS $ext" >/dev/null 2>&1 \
      && ok "$ext установлено" \
      || die "не удалось создать расширение $ext — нужен запрос провайдеру"
  fi
done

echo
echo "── Миграции ─────────────────────────────────────────────────────────"
for f in 01_extensions.sql 02_schema.sql 03_rls.sql; do
  [ -f "$INIT/$f" ] || die "нет файла $INIT/$f"
  echo "   применяю $f"
  "${PSQL[@]}" -f "$INIT/$f" >/dev/null
  ok "$f"
done

echo
echo "── Логин-роли ───────────────────────────────────────────────────────"
# Аналог 04_login_role.sh, но через внешнее соединение и с паролями,
# переданными как параметры psql, а не подставленные в текст SQL.
"${PSQL[@]}" \
  -v app_password="$AGORA_APP_PASSWORD" \
  -v share_password="$AGORA_SHARE_PASSWORD" \
  -v dbname="$(q 'SELECT current_database()')" <<'EOSQL' >/dev/null
-- Существующая роль проверяется, а не переписывается: NOSUPERUSER и NOBYPASSRLS
-- умеет ставить только суперпользователь, причём даже когда атрибут уже снят.
-- На managed-инстансе выданная роль суперпользователем не является, и прежний
-- безусловный ALTER останавливал скрипт на роли, которая и так была в порядке.
DO $$
DECLARE r record;
BEGIN
  SELECT rolsuper, rolbypassrls INTO r FROM pg_roles WHERE rolname = 'agora_login';
  IF NOT FOUND THEN
    CREATE ROLE agora_login LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  ELSIF r.rolsuper OR r.rolbypassrls THEN
    RAISE EXCEPTION 'роль agora_login имеет SUPERUSER или BYPASSRLS — приложение обходило бы RLS. Снимите атрибуты суперпользователем: ALTER ROLE agora_login NOSUPERUSER NOBYPASSRLS';
  END IF;
END
$$;
ALTER ROLE agora_login PASSWORD :'app_password';
-- NOINHERIT обязателен: без него соединение получает права agora_app сразу,
-- и забытый SET LOCAL ROLE перестаёт быть заметен. Менять этот атрибут
-- суперпользователем быть не нужно — достаточно прав владельца роли.
ALTER ROLE agora_login NOINHERIT;
GRANT agora_app   TO agora_login;
GRANT agora_share TO agora_login;

DO $$
DECLARE r record;
BEGIN
  SELECT rolsuper, rolbypassrls INTO r FROM pg_roles WHERE rolname = 'agora_share_login';
  IF NOT FOUND THEN
    CREATE ROLE agora_share_login LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
  ELSIF r.rolsuper OR r.rolbypassrls THEN
    RAISE EXCEPTION 'роль agora_share_login имеет SUPERUSER или BYPASSRLS';
  END IF;
END
$$;
ALTER ROLE agora_share_login PASSWORD :'share_password';
GRANT agora_share TO agora_share_login;

GRANT CONNECT ON DATABASE :"dbname" TO agora_login, agora_share_login;
EOSQL
ok "agora_login и agora_share_login готовы"

echo
echo "── Аутентификация (задача #3) ───────────────────────────────────────"
# 05_auth.sql идёт ПОСЛЕ создания ролей, а не в общем цикле миграций: он раздаёт
# GRANT EXECUTE роли agora_app, а до предыдущего блока такой роли не существует.
# Порядок здесь не косметика — GRANT несуществующей роли останавливает скрипт.
if [ -f "$INIT/05_auth.sql" ]; then
  echo "   применяю 05_auth.sql"
  "${PSQL[@]}" -f "$INIT/05_auth.sql" >/dev/null
  ok "05_auth.sql"
else
  warn "нет $INIT/05_auth.sql — вход по паролю работать не будет"
fi

# 06_owner_read_auth_tables.sql — политики SELECT для владельца на teams и
# team_members. FORCE RLS остаётся. Без этой политики SECURITY DEFINER функции
# не могут читать таблицы при логине (tenant_id ещё не установлен).
if [ -f "$INIT/06_owner_read_auth_tables.sql" ]; then
  echo "   применяю 06_owner_read_auth_tables.sql"
  "${PSQL[@]}" -f "$INIT/06_owner_read_auth_tables.sql" >/dev/null
  ok "06_owner_read_auth_tables.sql"
fi

# 07_prompts_seed.sql — засев дефолтных промптов (задача #26). Идемпотентен:
# ON CONFLICT DO NOTHING, повторный прогон не плодит строки и не затирает
# пользовательские версии. Без этой миграции Промпт-студия на существующей базе
# пуста — таблица prompts есть (из 02_schema.sql), а строк в ней нет, и
# резолверу некому вернуть дефолт. Выполняется от имени владельца вне RLS-контекста.
if [ -f "$INIT/07_prompts_seed.sql" ]; then
  echo "   применяю 07_prompts_seed.sql"
  "${PSQL[@]}" -f "$INIT/07_prompts_seed.sql" >/dev/null
  ok "07_prompts_seed.sql"
else
  warn "нет $INIT/07_prompts_seed.sql — Промпт-студия будет без дефолтных промптов (задача #26)"
fi

# 08_portrait_versions.sql — история версий портретов аудиторий (задача #24).
# CREATE TABLE IF NOT EXISTS, политика изоляции по арендатору, GRANT для agora_app —
# та же схема, что у остальных шестнадцати таблиц. FORCE RLS не снимается.
# Выполняется от имени владельца вне RLS-контекста.
if [ -f "$INIT/08_portrait_versions.sql" ]; then
  echo "   применяю 08_portrait_versions.sql"
  "${PSQL[@]}" -f "$INIT/08_portrait_versions.sql" >/dev/null
  ok "08_portrait_versions.sql"
else
  warn "нет $INIT/08_portrait_versions.sql — история версий портретов недоступна (задача #24)"
fi

# 09_task_idempotency.sql — ключ идемпотентности запуска (задача #11).
# ADD COLUMN IF NOT EXISTS + частичный уникальный индекс по (tenant_id, ключ).
# Без него двойной клик по «Запустить» порождает второй платный прогон, а
# отличить его от намеренного повтора нечем.
if [ -f "$INIT/09_task_idempotency.sql" ]; then
  echo "   применяю 09_task_idempotency.sql"
  "${PSQL[@]}" -f "$INIT/09_task_idempotency.sql" >/dev/null
  ok "09_task_idempotency.sql"
else
  warn "нет $INIT/09_task_idempotency.sql — запуск исследования не идемпотентен (задача #11)"
fi

# 10_prompts_seed_persona_enrich.sql — промпт обогащения персон моделью.
# Без него генерация аудитории работает, но портреты остаются шаблонными:
# enrich.py не находит промпт и деградирует молча — то есть дефект выглядит как
# «модель пишет скучно», а не как незасеянная строка.
if [ -f "$INIT/10_prompts_seed_persona_enrich.sql" ]; then
  echo "   применяю 10_prompts_seed_persona_enrich.sql"
  "${PSQL[@]}" -f "$INIT/10_prompts_seed_persona_enrich.sql" >/dev/null
  ok "10_prompts_seed_persona_enrich.sql"
else
  warn "нет $INIT/10_prompts_seed_persona_enrich.sql — портреты персон будут шаблонными"
fi

echo
echo "── Итог ─────────────────────────────────────────────────────────────"
# users — единственная таблица без tenant_id: глобальная идентичность, к
# арендатору не привязана (02_schema.sql, 03_rls.sql). RLS по арендатору на ней
# бессмысленна, ограничивает её Auth.js и прикладной код.
#
# Исключение перечислено здесь, а не проверяется «на глаз», по конкретной
# причине: до этой правки итог всегда печатал WARN «не на всех таблицах включён
# FORCE RLS», потому что users в счёт попадала. Предупреждение, которое горит
# всегда, перестают читать — и настоящая таблица без FORCE прошла бы незамеченной
# ровно тем же текстом.
RLS_EXEMPT="'users'"

TABLES=$(q "SELECT count(*) FROM pg_tables
             WHERE schemaname = 'public' AND tablename NOT IN ($RLS_EXEMPT)")
RLS_ON=$(q "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
              AND c.relname NOT IN ($RLS_EXEMPT)
              AND c.relrowsecurity AND c.relforcerowsecurity")
POLICIES=$(q "SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
ok "таблиц: $TABLES · с FORCE RLS: $RLS_ON · политик: $POLICIES · вне RLS: users"

if [ "$TABLES" != "$RLS_ON" ]; then
  MISSING=$(q "SELECT string_agg(c.relname, ', ' ORDER BY c.relname)
                 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND c.relname NOT IN ($RLS_EXEMPT)
                  AND NOT (c.relrowsecurity AND c.relforcerowsecurity)")
  die "FORCE RLS отсутствует на таблицах: $MISSING — они доступны владельцу целиком"
fi

echo
echo "Дальше:"
echo "  1. python3 evals/check.py                     — метрика rls_tenant должна стать pass"
echo "  2. заведите владельца команды (задача #3):"
echo "     node apps/web/scripts/seed-auth.mjs --team 'Моя команда' \\"
echo "          --email you@example.com --password '…'"
echo "     без него войти некем: самостоятельной регистрации в продукте нет."
