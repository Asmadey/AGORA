"""
Сборщик мусора во внешних хранилищах: S3, Mongo и слепки корпуса.

─── Что чинится ─────────────────────────────────────────────────────────────
11.09.2026 на боевой базе, где не осталось ни одного исследования, лежало:
864 кадра тридцати шести удалённых прогонов (61.6 МБ), 11 роликов, которым не
принадлежит ни один прогон (189.2 МБ), 49 документов Mongo тех же прогонов и
59 слепков корпуса без единой ссылки.

Заметить это было неоткуда. Исследование пропадает из списка, экран чист,
место занято, а счёт за хранилище приходит раз в месяц и не объясняет, чем.

─── Почему уборки на месте недостаточно ─────────────────────────────────────
`DELETE /api/tasks/{id}` убирает строку Postgres последней и честно пишет, что
отказ внешнего хранилища удаления не отменяет. Порядок выбран верно: любой
обрыв оставляет мусор, а не исследование, ссылающееся на удалённые данные.

Цена названа там же: «строки уже нет, и возвращать ошибку значило бы предлагать
повторить операцию, которая не повторяется». Повторять действительно нечем —
адреса объектов жили в строке и в пакете материала, которых больше нет.

Поэтому повтор идёт С ДРУГОЙ СТОРОНЫ: не от строки к объектам, а от объектов к
строке. Ключ `tenants/<t>/runs/<task>/frames/...` несёт идентификатор прогона в
себе, документ Mongo несёт `task_id` полем — этого достаточно, чтобы спросить у
базы, жив ли прогон.

─── Чего сборщик не делает ──────────────────────────────────────────────────
**Не удаляет по умолчанию.** Сухой прогон — умолчание, `--apply` — явное
решение. Так же устроены сборщик осиротевших прогонов и сборщик зомби.

**Не трогает то, чего не понял.** Ключ, который не разобрался, остаётся на
месте. Догадка о чужом формате стоит дороже гигабайта.

**Не трогает свежие загрузки.** Ролик попадает в хранилище ДО того, как
появляется строка прогона: пользователь загружает файл, потом запускает
исследование. Сборщик без отсрочки удалял бы файл у него из-под рук, и выглядело
бы это случайным сбоем загрузки, а не уборкой.

**Не трогает `chunk_analyses`.** Это кэш по хэшу содержимого, у него нет и не
должно быть `task_id`: он переживает прогоны намеренно. Запись без `task_id` для
сборщика — не сирота, а чужая территория.

─── Что охраняется главным ──────────────────────────────────────────────────
Пустое множество живых прогонов означает «всё осиротело» ТОЛЬКО тогда, когда
таблица прочитана успешно. `None` — это «не знаю», и оно не равно «живых нет»;
разница между ними — всё хранилище целиком.

Отсюда `ValueError` вместо тихой уборки. Эта сессия нашла три дефекта одного
вида — пустой список, прошедший за успех: список проверок CI между запусками,
`grep` по чужому образцу вывода, код возврата, съеденный конвейером. Ни один не
имел прав на удаление. У этого модуля они есть.
"""

from __future__ import annotations

import argparse
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

#: Сколько загрузка вправе пролежать без ссылки, прежде чем считаться сиротой.
#:
#: Сутки — запас на порядок к настоящему промежутку между загрузкой файла и
#: появлением строки прогона (секунды, в худшем случае минуты, если человек
#: отвлёкся посреди мастера). Ошибка в сторону терпения стоит места; ошибка в
#: обратную сторону стоит пользовательского файла.
UPLOAD_GRACE_SEC = 24 * 60 * 60

#: Ключ кадра: `tenants/<uuid>/runs/<uuid>/...`.
#:
#: Идентификаторы сверяются как UUID, а не как «что угодно до косой черты»:
#: непонятый ключ обязан остаться непонятым, а не превратиться в сироту с
#: выдуманным именем прогона.
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_RUN_KEY = re.compile(rf"^tenants/({_UUID})/runs/({_UUID})/")

#: Коллекции Mongo, которые принадлежат прогону и уходят вместе с ним.
#:
#: `chunk_analyses` здесь нет намеренно — см. заголовок. `wizard_drafts` тоже:
#: черновик мастера существует ДО прогона и по определению ни на какой не
#: ссылается.
RUN_COLLECTIONS = ("reports", "report_personas", "content_packs")


@dataclass(frozen=True)
class StoredObject:
    """Объект хранилища: ключ, размер и возраст."""

    key: str
    size: int
    age_sec: float


def _known(value: Any, what: str) -> Any:
    """
    `None` — это «не знаю», и оно не равно «пусто».

    Функция существует затем, чтобы разница между ними была написана один раз
    и проверялась во всех трёх местах одинаково.
    """
    if value is None:
        raise ValueError(
            f"{what} не прочитано. Пустой ответ и неудачное чтение выглядят "
            f"одинаково, а стоят по-разному: сборщик не убирает вслепую."
        )
    return value


def parse_run_key(key: str) -> tuple[str, str] | None:
    """Арендатор и прогон из ключа объекта. `None` — ключ не про прогон."""
    if not key:
        return None
    m = _RUN_KEY.match(key)
    return (m.group(1), m.group(2)) if m else None


def orphan_run_objects(
    keys: Iterable[str],
    *,
    live_task_ids: set[str] | None,
) -> list[str]:
    """Ключи прогонов, которых больше нет. Непонятые ключи не возвращаются."""
    live = _known(live_task_ids, "множество живых прогонов")
    orphans = []
    for key in keys:
        parsed = parse_run_key(key)
        if parsed is None:
            continue
        if parsed[1] not in live:
            orphans.append(key)
    return orphans


def orphan_uploads(
    objects: Iterable[StoredObject],
    *,
    referenced: set[str] | None,
    grace_sec: float = UPLOAD_GRACE_SEC,
) -> list[str]:
    """Загрузки без ссылки и старше отсрочки."""
    refs = _known(referenced, "множество ссылок на загрузки")
    return [
        o.key for o in objects if o.key not in refs and o.age_sec >= grace_sec
    ]


def orphan_snapshots(
    snapshot_ids: Iterable[str],
    *,
    referenced: set[str] | None,
) -> list[str]:
    """
    Слепки, на которые не смотрит ни один набор.

    `persona_sets.corpus_snapshot_id` объявлен `ON DELETE SET NULL`: удаление
    набора обнуляет ссылку и оставляет слепок. После этого найти его нечем — на
    него не ссылается уже ничто, а сам он не знает, чей он был.
    """
    refs = _known(referenced, "множество ссылок на слепки")
    return sorted(set(snapshot_ids) - refs)


# ─── Обвязка: чтение живых прогонов и удаление ──────────────────────────────


def assert_full_task_visibility(conn: Any) -> None:
    """
    Убедиться, что роль видит прогоны ВСЕХ статусов, а не только идущие.

    Миграция 41 выдала владельцу схемы `SELECT ... USING (status = 'RUNNING')`
    — ровно то, что нужно сборщику осиротевших прогонов, и ровно то, что этому
    сборщику смертельно: под такой политикой в тихий час `SELECT id FROM tasks`
    возвращает пусто, а пусто здесь означает «удалить всё».

    Проверяются два законных основания видеть всё: роль обходит RLS (так на
    боевой машине, где владелец — суперпользователь) либо у неё есть политика
    на `tasks` без ограничения по строкам. Ни того, ни другого — отказ.

    Отказ, а не предупреждение: сборщик с правами на удаление и с неполной
    картиной опаснее, чем сборщик, который не запустился.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = current_user"
        )
        row = cur.fetchone()
        if row and row[0]:
            return

        # `qual IS NULL` у политики SELECT означает USING (true) — без
        # ограничения по строкам. Политика со строковым условием сюда не
        # попадает намеренно: именно она и есть источник ошибки.
        cur.execute(
            """
            SELECT count(*) FROM pg_policies
             WHERE schemaname = 'public' AND tablename = 'tasks'
               AND cmd IN ('SELECT', 'ALL')
               AND qual IS NULL
               AND current_user = ANY (roles)
            """
        )
        row = cur.fetchone()
        if row and row[0]:
            return

    raise RuntimeError(
        "роль видит не все прогоны: под политикой миграции 41 владельцу схемы "
        "видны только RUNNING, и пустой ответ означал бы «удалить всё». "
        "Нужна миграция 42 (узкий SELECT на tasks) либо роль, обходящая RLS."
    )


def _live_task_ids(conn: Any) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id::text FROM tasks")
        return {row[0] for row in cur.fetchall()}


def _referenced_uploads(conn: Any) -> set[str]:
    """Все ключи, на которые смотрит хоть одна строка прогона."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT video_ref FROM tasks WHERE video_ref IS NOT NULL
            UNION SELECT playback_ref FROM tasks WHERE playback_ref IS NOT NULL
            UNION SELECT poster_ref FROM tasks WHERE poster_ref IS NOT NULL
            UNION SELECT s3_key FROM audience_context_files
            """
        )
        return {row[0] for row in cur.fetchall()}


def _snapshot_state(conn: Any) -> tuple[set[str], set[str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id::text FROM corpus_snapshots")
        all_ids = {row[0] for row in cur.fetchall()}
        cur.execute(
            "SELECT corpus_snapshot_id::text FROM persona_sets "
            "WHERE corpus_snapshot_id IS NOT NULL"
        )
        refs = {row[0] for row in cur.fetchall()}
    return all_ids, refs


def _list_objects(s3: Any, bucket: str) -> list[StoredObject]:
    now = time.time()
    out: list[StoredObject] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            out.append(
                StoredObject(
                    key=obj["Key"],
                    size=obj["Size"],
                    age_sec=now - obj["LastModified"].timestamp(),
                )
            )
    return out


def sweep(
    *,
    apply: bool = False,
    conn: Any = None,
    s3: Any = None,
    bucket: str | None = None,
    mongo: Any = None,
) -> dict[str, Any]:
    """
    Полный проход по трём хранилищам.

    Соединения принимаются параметрами, а не создаются внутри: так проход
    проверяется поддельными, и так же его зовёт задача Celery, у которой они
    уже есть.
    """
    report: dict[str, Any] = {"apply": apply}

    # Живые прогоны читаются ОДИН раз и до всего остального: если чтение не
    # удалось, падать надо до первого удаления, а не после половины.
    if conn is not None:
        assert_full_task_visibility(conn)
    live = _live_task_ids(conn) if conn is not None else None

    if s3 is not None and bucket:
        objects = _list_objects(s3, bucket)
        by_key = {o.key: o for o in objects}

        run_orphans = orphan_run_objects(
            (o.key for o in objects), live_task_ids=live
        )
        upload_orphans = orphan_uploads(
            [o for o in objects if "/uploads/" in o.key],
            referenced=_referenced_uploads(conn) if conn is not None else None,
        )
        keys = run_orphans + upload_orphans
        report["s3"] = {
            "кадров прогонов": len(run_orphans),
            "загрузок": len(upload_orphans),
            "байт": sum(by_key[k].size for k in keys),
        }
        if apply:
            deleted, failed = 0, []
            for key in keys:
                try:
                    s3.delete_object(Bucket=bucket, Key=key)
                    deleted += 1
                except Exception as e:  # noqa: BLE001 — отказ на одном ключе
                    failed.append(f"{key}: {e}")  # не должен уносить остальные
            report["s3"]["удалено"] = deleted
            report["s3"]["не удалось"] = failed

    if mongo is not None:
        mongo_report: dict[str, Any] = {}
        for name in RUN_COLLECTIONS:
            coll = mongo[name]
            ids = {str(t) for t in coll.distinct("task_id") if t}
            dead = ids - _known(live, "множество живых прогонов")
            count = coll.count_documents({"task_id": {"$in": sorted(dead)}}) if dead else 0
            mongo_report[name] = count
            if apply and dead:
                coll.delete_many({"task_id": {"$in": sorted(dead)}})
        report["mongo"] = mongo_report

    if conn is not None:
        all_snaps, refs = _snapshot_state(conn)
        dead_snaps = orphan_snapshots(all_snaps, referenced=refs)
        report["слепки"] = len(dead_snaps)
        if apply and dead_snaps:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM corpus_snapshots WHERE id = ANY(%s::uuid[])",
                    (dead_snaps,),
                )
            conn.commit()

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Сборщик мусора во внешних хранилищах"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="только показать (по умолчанию)"
    )
    mode.add_argument("--apply", action="store_true", help="удалить найденное")
    args = parser.parse_args()

    import os

    import psycopg

    from ..mongo import mongo_db
    from ..storage import Boto3S3

    # Владелец схемы, а не роль приложения: обход всех арендаторов под
    # `agora_app` невозможен по замыслу. Переменная та же, что у сборщика
    # осиротевших прогонов, — третий секрет ради уборки не заводится.
    dsn = os.environ.get("POSTGRES_ADMIN_URL")
    if not dsn:
        raise RuntimeError(
            "POSTGRES_ADMIN_URL не задан — сборщику нужен владелец схемы"
        )

    s3 = Boto3S3()
    with psycopg.connect(dsn) as conn:
        result = sweep(
            apply=args.apply,
            conn=conn,
            s3=s3.client,
            bucket=s3.bucket,
            mongo=mongo_db(),
        )

    print(f"Слепки корпуса без ссылок: {result.get('слепки', 0)}")
    s3r = result.get("s3", {})
    if s3r:
        mb = s3r["байт"] / 1024 / 1024
        print(
            f"S3: кадров {s3r['кадров прогонов']}, загрузок {s3r['загрузок']}, "
            f"{mb:.1f} МБ"
        )
        if s3r.get("не удалось"):
            for line in s3r["не удалось"]:
                print(f"  не удалено — {line}")
    for name, count in result.get("mongo", {}).items():
        print(f"Mongo {name}: {count}")
    if not args.apply:
        print("Сухой прогон: ничего не удалено. Удаление — с --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
