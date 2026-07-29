"""Слой доступа к Postgres с обязательным тенант-контекстом (задача #2).

Замысел: сделать утечку между арендаторами структурно невозможной, а не «мы помним,
что надо фильтровать». Единственный способ получить курсор — через `tenant_scope()`,
который открывает транзакцию, переключается на ограниченную роль и выставляет
`app.tenant_id`. Забыть фильтр нельзя: фильтрует не код, а RLS-политика в базе.

Почему SET LOCAL, а не SET:
    SET LOCAL живёт до конца транзакции. При работе через пул соединение возвращается
    в пул с чистым состоянием, и следующий арендатор не унаследует чужой контекст.
    Обычный SET оставил бы контекст на соединении — ровно тот класс ошибок, который
    даёт кросс-арендаторную утечку под нагрузкой, а не в тестах.

Почему SET LOCAL ROLE:
    RLS не действует на суперпользователя и на владельца таблиц. Подключаться можно
    хоть под миграционной ролью, но работать обязаны под agora_app (NOSUPERUSER,
    NOBYPASSRLS). Переключение роли внутри транзакции откатывается вместе с ней.
"""
from __future__ import annotations

import contextlib
import hashlib
import re
import uuid
from collections.abc import Iterator
from typing import Any

APP_ROLE = "agora_app"
SHARE_ROLE = "agora_share"

# Имена ролей подставляются в SQL идентификатором, а не параметром, поэтому
# допускаем только безопасный алфавит. Паранойя дешевле инцидента.
_SAFE_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


class TenantContextError(RuntimeError):
    """Попытка работать с базой без корректного тенант-контекста."""


def _validate_role(role: str) -> str:
    if not _SAFE_IDENT.match(role):
        raise TenantContextError(f"недопустимое имя роли: {role!r}")
    return role


def _coerce_tenant_id(tenant_id: Any) -> uuid.UUID:
    """Приводит арендатора к UUID и отвергает всё остальное.

    Строка произвольного вида до базы дойти не должна: пусть падает здесь,
    с внятным сообщением, а не превращается в NULL внутри политики — потому что
    NULL в политике означает «ничего не видно», и такую ошибку легко принять
    за пустую базу.
    """
    if isinstance(tenant_id, uuid.UUID):
        return tenant_id
    if isinstance(tenant_id, str):
        try:
            return uuid.UUID(tenant_id)
        except ValueError as e:
            raise TenantContextError(f"tenant_id не является UUID: {tenant_id!r}") from e
    raise TenantContextError(
        f"tenant_id должен быть UUID или строкой, получен {type(tenant_id).__name__}"
    )


def hash_share_token(token: str) -> str:
    """SHA-256 токена публичной ссылки.

    Тот же алгоритм, что в app.current_share_token_hash() на стороне базы.
    В базе хранится только хеш — дамп базы не даёт доступа по ссылкам.
    """
    if not token:
        raise TenantContextError("пустой токен публичной ссылки")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@contextlib.contextmanager
def tenant_scope(conn: Any, tenant_id: Any, *, role: str = APP_ROLE) -> Iterator[Any]:
    """Транзакция, ограниченная одним арендатором.

    Использование::

        with tenant_scope(conn, tenant_id) as cur:
            cur.execute("SELECT * FROM projects")   # вернёт только свои строки

    Никакого `WHERE tenant_id = ...` писать не нужно и не следует: фильтрацию
    выполняет RLS. Если политика вдруг отключена, запрос вернёт лишнее — и это
    поймает поведенческий тест изоляции, а не прикладной код.
    """
    tid = _coerce_tenant_id(tenant_id)
    safe_role = _validate_role(role)

    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL ROLE {safe_role}")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tid),))
            yield cur


@contextlib.contextmanager
def share_scope(conn: Any, token: str) -> Iterator[Any]:
    """Транзакция для публичной страницы расшаренного отчёта (#29).

    Работает под ролью agora_share и без тенант-контекста: единственный
    санкционированный обход тенант-изоляции во всей системе. Что именно окажется
    видно, решает политика reports_public_share_read — она же проверяет, что
    ссылка не отозвана и не истекла. Здесь мы передаём токен, а не его хеш:
    хеширование делает сама база, чтобы алгоритм не разъехался между слоями.
    """
    if not token:
        raise TenantContextError("публичная ссылка требует токен")

    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL ROLE {SHARE_ROLE}")
            cur.execute("SELECT set_config('app.share_token', %s, true)", (token,))
            yield cur


def assert_tenant_filter(collection_filter: dict[str, Any]) -> dict[str, Any]:
    """Страховка для MongoDB, где RLS не существует.

    В Postgres забыть фильтр безопасно — поймает политика. В Mongo забыть фильтр
    означает выдать чужие данные, поэтому каждый запрос обязан пройти через эту
    проверку. Вызывать в репозиториях коллекций, а не «по возможности».
    """
    tenant_id = collection_filter.get("tenant_id")
    if tenant_id is None:
        raise TenantContextError(
            "запрос к MongoDB без tenant_id: в Mongo нет RLS, изоляцию обеспечивает только код"
        )
    _coerce_tenant_id(tenant_id)
    return collection_filter
