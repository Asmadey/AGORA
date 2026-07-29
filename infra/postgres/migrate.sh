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
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agora_login') THEN
    CREATE ROLE agora_login LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  ELSE
    ALTER ROLE agora_login LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;
ALTER ROLE agora_login PASSWORD :'app_password';
ALTER ROLE agora_login NOINHERIT;
GRANT agora_app   TO agora_login;
GRANT agora_share TO agora_login;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agora_share_login') THEN
    CREATE ROLE agora_share_login LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END
$$;
ALTER ROLE agora_share_login PASSWORD :'share_password';
GRANT agora_share TO agora_share_login;

GRANT CONNECT ON DATABASE :"dbname" TO agora_login, agora_share_login;
EOSQL
ok "agora_login и agora_share_login готовы"

echo
echo "── Итог ─────────────────────────────────────────────────────────────"
TABLES=$(q "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
RLS_ON=$(q "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity AND c.relforcerowsecurity")
POLICIES=$(q "SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
ok "таблиц: $TABLES · с FORCE RLS: $RLS_ON · политик: $POLICIES"

if [ "$TABLES" != "$RLS_ON" ]; then
  warn "не на всех таблицах включён FORCE RLS — таблица без него доступна владельцу целиком"
fi

echo
echo "Дальше: подставьте AGORA_APP_PASSWORD в DATABASE_URL (percent-encoded)"
echo "и запустите  python3 evals/check.py  — метрика rls_tenant должна стать pass."
