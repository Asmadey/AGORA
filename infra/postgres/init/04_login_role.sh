#!/bin/bash
# AGORA · 04 · логин-роль приложения
# Задача #2. Запускается официальным энтрипойнтом Postgres после *.sql того же каталога.
#
# Зачем отдельный скрипт, а не SQL: пароли берутся из окружения и не должны
# попадать в файл миграции, который уедет в git.
#
# Модель ролей:
#   postgres      — суперпользователь, только миграции. RLS его не касается вообще.
#   agora_login   — под ней подключаются web и worker. Сама по себе прав не имеет.
#   agora_app     — рабочая роль (NOSUPERUSER NOBYPASSRLS). Переключение через SET LOCAL ROLE.
#   agora_share   — публичная страница расшаренного отчёта, только чтение по токену.
#
# Смысл разделения: соединение открывается безвластной ролью, а права появляются
# только внутри транзакции и умирают вместе с ней. Забытый SET LOCAL ROLE даёт
# отказ в доступе, а не тихую выдачу чужих данных.

set -euo pipefail

: "${AGORA_APP_PASSWORD:?AGORA_APP_PASSWORD обязателен}"
: "${AGORA_SHARE_PASSWORD:?AGORA_SHARE_PASSWORD обязателен}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v app_password="$AGORA_APP_PASSWORD" \
     -v share_password="$AGORA_SHARE_PASSWORD" <<-'EOSQL'

    -- Логин-роль для приложения. Прав не имеет: только право стать agora_app
    -- или agora_share внутри транзакции.
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

    -- Членство даёт право на SET ROLE. INHERIT выключен намеренно: без явного
    -- SET LOCAL ROLE соединение не получает прав ни одной из рабочих ролей.
    ALTER ROLE agora_login NOINHERIT;
    GRANT agora_app   TO agora_login;
    GRANT agora_share TO agora_login;

    -- Отдельная логин-роль под публичные страницы — на случай, если фронт
    -- захочет держать для них независимый пул соединений.
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agora_share_login') THEN
        CREATE ROLE agora_share_login LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
      END IF;
    END
    $$;
    ALTER ROLE agora_share_login PASSWORD :'share_password';
    GRANT agora_share TO agora_share_login;

    -- Подключаться к базе можно, создавать объекты в public — нельзя.
    GRANT CONNECT ON DATABASE :"POSTGRES_DB" TO agora_login, agora_share_login;
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;

EOSQL

echo "AGORA: логин-роли agora_login и agora_share_login готовы"
