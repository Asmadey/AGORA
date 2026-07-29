#!/usr/bin/env python3
"""AGORA · preflight: доступность внешней инфраструктуры.

    set -a; source .env.local; set +a
    python3 infra/preflight.py

Проверяет четыре сервиса по отдельности и печатает, что именно сломано. Смысл
в раздельности: «приложение не стартует» — бесполезная диагностика, когда
хранилищ четыре и упасть может любое. Скрипт не чинит и не мигрирует, только
отвечает на вопрос «дотягиваемся ли и теми ли учётными данными».

Зависимости ставятся по необходимости; отсутствующая библиотека — это SKIP,
а не FAIL: неустановленный psycopg ничего не говорит о состоянии базы.
"""
from __future__ import annotations

import os
import socket
import sys
from urllib.parse import urlparse

GRN, RED, YEL, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

results: list[tuple[str, str, str]] = []


def report(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    mark = {"ok": f"{GRN}  OK{OFF}", "fail": f"{RED}FAIL{OFF}", "skip": f"{YEL}SKIP{OFF}"}[status]
    print(f"{mark}  {name:12} {detail}")


def tcp(host: str, port: int, timeout: float = 6.0) -> str | None:
    """Отдельная проверка TCP до прикладной: различает «сеть закрыта» и «пароль не тот»."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return None
    except OSError as e:
        return str(e)


def check_postgres() -> None:
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_ADMIN_URL")
    if not url:
        return report("postgres", "skip", "ни DATABASE_URL, ни POSTGRES_ADMIN_URL не заданы")
    if "CHANGE_ME" in url:
        return report("postgres", "skip", "в строке подключения остался CHANGE_ME")

    p = urlparse(url)
    err = tcp(p.hostname or "", p.port or 5432)
    if err:
        return report("postgres", "fail", f"TCP {p.hostname}:{p.port or 5432} — {err}")

    try:
        import psycopg
    except ImportError:
        return report("postgres", "skip", f"TCP доступен; psycopg не установлен {DIM}(pip install 'psycopg[binary]'){OFF}")

    try:
        with psycopg.connect(url, connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database(), count(*) FROM pg_tables WHERE schemaname='public'")
            user, db, tables = cur.fetchone()
            cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname='public'")
            (policies,) = cur.fetchone()
        detail = f"{user}@{db} · таблиц {tables} · политик RLS {policies}"
        if tables == 0:
            return report("postgres", "fail", detail + " — схема не применена, см. infra/postgres/migrate.sh")
        report("postgres", "ok", detail)
    except Exception as e:  # noqa: BLE001 — печатаем причину как есть, она информативна
        report("postgres", "fail", str(e).strip().splitlines()[0])


def check_mongo() -> None:
    url = os.environ.get("MONGODB_URL")
    if not url:
        return report("mongodb", "skip", "MONGODB_URL не задан")

    p = urlparse(url)
    err = tcp(p.hostname or "", p.port or 27017)
    if err:
        return report("mongodb", "fail", f"TCP {p.hostname}:{p.port or 27017} — {err}")

    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
    except ImportError:
        return report("mongodb", "skip", f"TCP доступен; pymongo не установлен {DIM}(pip install pymongo){OFF}")

    try:
        client = MongoClient(url, serverSelectionTimeoutMS=8000)
        info = client.admin.command("ping")
        db = client.get_default_database()
        names = db.list_collection_names() if db is not None else []
        report("mongodb", "ok", f"ping={info.get('ok')} · коллекций {len(names)}")
    except PyMongoError as e:
        report("mongodb", "fail", str(e).strip().splitlines()[0])


def check_redis() -> None:
    url = os.environ.get("VALKEY_URL")
    if not url:
        return report("redis", "skip", "VALKEY_URL не задан")

    p = urlparse(url)
    err = tcp(p.hostname or "", p.port or 6379)
    if err:
        return report("redis", "fail", f"TCP {p.hostname}:{p.port or 6379} — {err}")

    try:
        import redis
    except ImportError:
        return report("redis", "skip", f"TCP доступен; redis не установлен {DIM}(pip install redis){OFF}")

    try:
        client = redis.from_url(url, socket_connect_timeout=8)
        client.ping()
        info = client.info("server")
        # Celery держит здесь и очередь, и результаты — вытеснение ключей по
        # памяти означало бы потерю прогона, поэтому политику стоит увидеть сразу.
        policy = client.config_get("maxmemory-policy").get("maxmemory-policy", "?")
        flavour = info.get("redis_version") or info.get("valkey_version") or "?"
        detail = f"v{flavour} · maxmemory-policy={policy}"
        if policy not in ("noeviction", "?"):
            detail += "  ← для очереди Celery нужен noeviction"
        report("redis", "ok", detail)
    except Exception as e:  # noqa: BLE001
        report("redis", "fail", str(e).strip().splitlines()[0])


def check_s3() -> None:
    endpoint = os.environ.get("S3_ENDPOINT")
    bucket = os.environ.get("S3_BUCKET")
    if not endpoint or not bucket:
        return report("s3", "skip", "S3_ENDPOINT или S3_BUCKET не заданы")

    try:
        import boto3
        from botocore.client import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return report("s3", "skip", f"boto3 не установлен {DIM}(pip install boto3){OFF}")

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
            region_name=os.environ.get("S3_REGION", "ru-1"),
            config=Config(signature_version="s3v4", connect_timeout=8, retries={"max_attempts": 1}),
        )
        s3.head_bucket(Bucket=bucket)
        listing = s3.list_objects_v2(Bucket=bucket, MaxKeys=1)
        report("s3", "ok", f"бакет доступен · объектов ≥ {listing.get('KeyCount', 0)}")
    except (ClientError, BotoCoreError) as e:
        report("s3", "fail", str(e).strip().splitlines()[0])


def main() -> int:
    print("AGORA preflight — проверка внешней инфраструктуры\n")
    check_postgres()
    check_mongo()
    check_redis()
    check_s3()

    failed = [n for n, s, _ in results if s == "fail"]
    skipped = [n for n, s, _ in results if s == "skip"]
    print()
    print(f"итог: ok={len(results) - len(failed) - len(skipped)} fail={len(failed)} skip={len(skipped)}")
    if skipped:
        print(f"{DIM}пропущено не значит исправно — доустановите клиенты и перезапустите{OFF}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
