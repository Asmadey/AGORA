"""Тесты слоя доступа с тенант-контекстом (задача #2).

Здесь проверяется контракт слоя без живой БД: что он выставляет ровно те команды,
которые нужны для RLS, и отвергает всё, что могло бы привести к утечке. Настоящая
кросс-арендаторная изоляция проверяется отдельно, на живом Postgres —
evals/tests/test_task02_db_rls.py.
"""
from __future__ import annotations

import hashlib
import uuid

import pytest

from agent_core.db import (
    APP_ROLE,
    SHARE_ROLE,
    TenantContextError,
    assert_tenant_filter,
    hash_share_token,
    share_scope,
    tenant_scope,
)


class FakeCursor:
    def __init__(self, log: list[tuple[str, tuple | None]]):
        self._log = log

    def execute(self, sql, params=None):
        self._log.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeTransaction:
    def __init__(self, log):
        self._log = log

    def __enter__(self):
        self._log.append(("BEGIN", None))
        return self

    def __exit__(self, *exc):
        self._log.append(("COMMIT", None))
        return False


class FakeConn:
    """Минимальная замена psycopg-соединения: пишет всё, что через неё прошло."""

    def __init__(self):
        self.log: list[tuple[str, tuple | None]] = []

    def transaction(self):
        return FakeTransaction(self.log)

    def cursor(self):
        return FakeCursor(self.log)


# ── тенант-контекст ───────────────────────────────────────────────────────


def test_tenant_scope_switches_role_and_sets_context():
    conn = FakeConn()
    tid = uuid.uuid4()

    with tenant_scope(conn, tid):
        pass

    statements = [sql for sql, _ in conn.log]
    assert statements[0] == "BEGIN"
    assert f"SET LOCAL ROLE {APP_ROLE}" in statements
    # Контекст ставится через set_config(..., true) — то есть is_local=true,
    # чтобы он умер вместе с транзакцией и не утёк в пул соединений.
    set_config = [(sql, p) for sql, p in conn.log if "set_config" in sql]
    assert len(set_config) == 1
    sql, params = set_config[0]
    assert "app.tenant_id" in sql
    assert params == (str(tid),)
    assert "true" in sql


def test_tenant_scope_accepts_string_uuid():
    conn = FakeConn()
    tid = str(uuid.uuid4())
    with tenant_scope(conn, tid):
        pass
    assert any(p == (tid,) for _, p in conn.log if p)


@pytest.mark.parametrize("bad", ["", "not-a-uuid", "1; DROP TABLE teams", "  "])
def test_tenant_scope_rejects_non_uuid(bad):
    conn = FakeConn()
    with pytest.raises(TenantContextError, match="UUID"):
        with tenant_scope(conn, bad):
            pass
    # Ни одной команды до базы дойти не должно.
    assert conn.log == []


@pytest.mark.parametrize("bad", [None, 42, 3.14, [], {}])
def test_tenant_scope_rejects_wrong_types(bad):
    conn = FakeConn()
    with pytest.raises(TenantContextError):
        with tenant_scope(conn, bad):
            pass


def test_tenant_scope_rejects_role_injection():
    """Имя роли уходит в SQL идентификатором, поэтому проверяется отдельно."""
    conn = FakeConn()
    with pytest.raises(TenantContextError, match="роли"):
        with tenant_scope(conn, uuid.uuid4(), role="agora_app; DROP TABLE teams --"):
            pass


# ── публичная ссылка ──────────────────────────────────────────────────────


def test_share_scope_uses_restricted_role_and_no_tenant():
    conn = FakeConn()
    with share_scope(conn, "secret-token"):
        pass

    statements = [sql for sql, _ in conn.log]
    assert f"SET LOCAL ROLE {SHARE_ROLE}" in statements
    # Публичный доступ идёт БЕЗ тенант-контекста: что видно, решает политика.
    assert not any("app.tenant_id" in sql for sql in statements)
    assert any("app.share_token" in sql for sql in statements)


def test_share_scope_requires_token():
    conn = FakeConn()
    with pytest.raises(TenantContextError):
        with share_scope(conn, ""):
            pass
    assert conn.log == []


def test_share_token_hash_matches_postgres_algorithm():
    """Хеш обязан совпадать с encode(digest(token,'sha256'),'hex') в SQL."""
    token = "6f1c0a4e-share"
    assert hash_share_token(token) == hashlib.sha256(token.encode()).hexdigest()
    assert len(hash_share_token(token)) == 64


def test_share_token_hash_rejects_empty():
    with pytest.raises(TenantContextError):
        hash_share_token("")


# ── страховка для MongoDB ─────────────────────────────────────────────────


def test_mongo_filter_requires_tenant_id():
    with pytest.raises(TenantContextError, match="нет RLS"):
        assert_tenant_filter({"task_id": "abc"})


def test_mongo_filter_validates_tenant_id_format():
    with pytest.raises(TenantContextError, match="UUID"):
        assert_tenant_filter({"tenant_id": "nope"})


def test_mongo_filter_passes_valid_filter():
    tid = str(uuid.uuid4())
    f = {"tenant_id": tid, "task_id": "abc"}
    assert assert_tenant_filter(f) is f
