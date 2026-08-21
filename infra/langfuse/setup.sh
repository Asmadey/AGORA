#!/usr/bin/env bash
#
# Пароли и ключи для LangFuse — генерируются на сервере и остаются на нём.
#
# Почему скриптом, а не руками. Значений шесть, три из них криптографические
# (SALT, ENCRYPTION_KEY, NEXTAUTH_SECRET) и требуют разной длины и кодировки.
# Придуманные вручную они выглядят так же, а работают иначе: ENCRYPTION_KEY
# короче 64 hex-символов LangFuse принимает и падает на первой расшифровке.
#
# Почему не в репозиторий. CLAUDE.md §7: всё, что попало в git или в переписку,
# считается скомпрометированным навсегда. Файл создаётся с правами 600 и лежит
# рядом с compose; ни одно значение не печатается в stdout.
#
# Повторный запуск безопасен: существующий .env не трогается. Перегенерация
# ENCRYPTION_KEY на живой базе сделала бы нечитаемыми все сохранённые ключи
# API — а понять это можно было бы только по тому, что трассировка перестала
# приходить.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$HERE/.env"

if [ -e "$ENV_FILE" ]; then
    echo "$ENV_FILE уже есть — оставляю как есть." >&2
    echo "Чтобы начать с нуля: удалите файл И тома langfuse_* (иначе старые" >&2
    echo "данные останутся зашифрованными ключом, которого больше нет)." >&2
    exit 0
fi

URL="${1:-https://langfuse.185-154-194-125.sslip.io}"

umask 077
{
    echo "# Сгенерировано infra/langfuse/setup.sh $(date -Is). В git не попадает."
    echo "LANGFUSE_URL=$URL"
    echo "LANGFUSE_DB_PASSWORD=$(openssl rand -hex 24)"
    echo "LANGFUSE_CLICKHOUSE_PASSWORD=$(openssl rand -hex 24)"
    echo "LANGFUSE_REDIS_PASSWORD=$(openssl rand -hex 24)"
    echo "LANGFUSE_MINIO_PASSWORD=$(openssl rand -hex 24)"
    echo "LANGFUSE_SALT=$(openssl rand -base64 32)"
    # Ровно 64 hex-символа — требование LangFuse, короче он принимает молча.
    echo "LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)"
    echo "LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -base64 32)"
    # Регистрация открыта, пока не заведён первый пользователь. Закрыть её —
    # отдельный шаг, и он обязателен: адрес публичный.
    echo "LANGFUSE_DISABLE_SIGNUP=false"
} > "$ENV_FILE"

chmod 600 "$ENV_FILE"
echo "готово: $ENV_FILE (права 600, содержимое не печатается)" >&2
