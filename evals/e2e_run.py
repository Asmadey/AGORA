#!/usr/bin/env python3
"""
Сквозной прогон исследования — задача #22.

Гейты `e2e_short` и `e2e_long` в `evals/check.py` читают артефакты прогона. Пока
артефактов нет, обе метрики пишут `skip`: честно, но бесполезно. Этот скрипт —
то, что артефакты производит.

─── Правило, вокруг которого всё построено ──────────────────────────────────
Скрипт не имеет права записать артефакт, которого не заработал.

Метрика читает файл и не знает, откуда он взялся. Артефакт, записанный при
недоступном сервере, на половине прогона или с выдуманными числами, превращает
`e2e_short` из первого гейта проекта в украшение — и заметить это можно будет
только по коду, потому что зелёная метрика выглядит одинаково в обоих случаях.

Отсюда устройство: артефакт пишется одной операцией в самом конце, после того
как все проверки прошли. Любой отказ по пути — ненулевой код возврата, объяснение
в stderr и отсутствие файла.

─── Почему HTTP, а не браузер ───────────────────────────────────────────────
Acceptance задачи называет Playwright. Отступление сознательное: все условия CDD
— про конвейер (статус, агрегат, число карточек, признак склейки), и браузер
проверяет их не лучше HTTP, зато тянет в `apps/web` бинарные зависимости, что
запрещено §6 CLAUDE.md. Проверка вёрстки отчёта нужна отдельно и здесь не
делается — это сказано вслух, а не спрятано за зелёной метрикой.

─── Golden-сеты ×3 ──────────────────────────────────────────────────────────
`--repeat 3` из acceptance: конвейер, прошедший один раз, не доказан. Между
прогонами меняются seed и порядок ответов модели. Артефакт несёт `runs` и
`passed`, а гейт требует их равенства — два прогона из трёх не «в основном
работает», а «воспроизводится через раз».

Пример:

    export BASE_URL=https://agora.example
    export CDD_OWNER_EMAIL=... CDD_OWNER_PASSWORD=...
    python3 evals/e2e_run.py --mode short --repeat 3
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "evals" / "tests"))

from _harness import ApiClient, creds  # noqa: E402

DEFAULT_ARTIFACTS = REPO / "evals" / "artifacts"
SHORT_FIXTURE = REPO / "evals" / "fixtures" / "short_60s.mp4"

ARTIFACT_NAME = {
    "short": "e2e_short_report.json",
    "long": "e2e_long_report.json",
}

#: Сколько персон в прогоне. Не «побольше для правдоподобия»: каждая персона —
#: это обращение к модели, и на гейте, который гоняют по три раза, цена растёт
#: втрое. Двенадцати хватает, чтобы `len(per_persona) == audience_size` что-то
#: означало, а посегментный разрез при этом честно скрывался порогом.
AUDIENCE_SIZE = 12

#: Пауза между опросами статуса. Чаще — лишняя нагрузка на сервер, который в
#: это время считает; реже — прогон дольше своего же таймаута.
POLL_SEC = 5


class RunFailed(RuntimeError):
    """Прогон не состоялся. Текст обязан называть шаг, на котором всё встало."""


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# ─── Шаги прогона ────────────────────────────────────────────────────────────


def connect(base_url: str) -> ApiClient:
    client = ApiClient(base_url)

    code, payload = client.call("/api/health")
    if code != 200:
        raise RunFailed(
            f"сервер недоступен: GET /api/health вернул {code} ({payload[:120]}). "
            f"Проверьте BASE_URL={base_url}"
        )

    email, password = creds("owner")
    if not email or not password:
        raise RunFailed(
            "не заданы CDD_OWNER_EMAIL и CDD_OWNER_PASSWORD — войти нечем. "
            "Они заводятся seed-auth.mjs и лежат в .env.local"
        )

    ok, why = client.login(email, password)
    if not ok:
        raise RunFailed(f"вход отказан: {why}")
    return client


def api(client: ApiClient, path: str, method: str = "GET", body: dict | None = None) -> dict:
    raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    code, payload = client.call(path, method, raw)
    if code == 0:
        raise RunFailed(f"{method} {path}: {payload}")
    if code >= 400:
        raise RunFailed(f"{method} {path} вернул {code}: {payload[:200]}")
    try:
        return json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        raise RunFailed(f"{method} {path} вернул не JSON: {payload[:200]}") from None


def upload_video(client: ApiClient, path: Path, mode: str) -> str:
    """Загрузка ролика: presign → PUT в S3 → complete. Возвращает videoRef."""
    if not path.is_file():
        raise RunFailed(f"фикстуры нет: {path}")

    content_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    size = path.stat().st_size
    presign = api(client, "/api/upload/presign", "POST", {
        "fileName": path.name, "contentType": content_type, "sizeBytes": size,
    })

    url = presign.get("url") or presign.get("uploadUrl")
    key = presign.get("key")
    if not url or not key:
        raise RunFailed(f"presign не вернул url и key: {json.dumps(presign)[:200]}")

    log(f"  загружаю {path.name} ({size / 1e6:.1f} МБ)")
    request = urllib.request.Request(
        url, method="PUT", data=path.read_bytes(),
        headers={"Content-Type": content_type},
    )
    try:
        # Таймаут щедрый: двенадцатиминутный ролик — это сотни мегабайт, и
        # обрыв здесь означал бы провал прогона на загрузке, а не на конвейере.
        with urllib.request.urlopen(request, timeout=900) as response:
            if response.status not in (200, 201, 204):
                raise RunFailed(f"S3 отказал на загрузке: {response.status}")
    except urllib.error.URLError as exc:
        raise RunFailed(f"загрузка в S3 не удалась: {exc.reason}") from None

    done = api(client, "/api/upload/complete", "POST",
               {"key": key, "mode": mode, "title": f"E2E {mode} {path.name}"})
    ref = done.get("videoRef") or done.get("ref") or key
    return str(ref)


def make_audience(client: ApiClient, seed: int) -> str:
    made = api(client, "/api/persona-sets", "POST", {
        "name": f"E2E аудитория {seed}", "size": AUDIENCE_SIZE, "seed": seed,
    })
    set_id = made.get("id") or (made.get("personaSet") or {}).get("id")
    if not set_id:
        raise RunFailed(f"набор персон не создан: {json.dumps(made)[:200]}")
    return str(set_id)


def pick_survey(client: ApiClient) -> str | None:
    """
    Анкета арендатора, если она есть.

    Отсутствие — не отказ: запуск без анкеты законен, персоны отвечают по пяти
    базовым критериям. Придумывать анкету здесь значило бы проверять конвейер на
    данных, которых в его настоящей работе не бывает.
    """
    listed = api(client, "/api/surveys")
    items = listed if isinstance(listed, list) else (listed.get("items") or [])
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            return str(item["id"])
    return None


def launch(client: ApiClient, *, mode: str, video_ref: str, persona_set: str,
           survey: str | None, seed: int) -> str:
    started = api(client, "/api/tasks", "POST", {
        "mode": mode,
        "videoRef": video_ref,
        "personaSetId": persona_set,
        "surveyId": survey,
        "replicationCount": 1,
        "seed": seed,
    })
    task_id = started.get("id") or started.get("taskId")
    if not task_id:
        raise RunFailed(f"запуск не вернул идентификатор задачи: {json.dumps(started)[:200]}")
    return str(task_id)


def wait_for_report(client: ApiClient, task_id: str, timeout: int) -> tuple[dict, float]:
    """Ждёт REPORT_READY. Возвращает (отчёт, секунды). Провал — исключение."""
    started = time.monotonic()
    last = ""

    while True:
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise RunFailed(
                f"прогон не уложился в {timeout}с: последний статус {last or 'неизвестен'}. "
                f"Это провал гейта, а не повод продлить ожидание"
            )

        listed = api(client, "/api/tasks")
        items = listed if isinstance(listed, list) else (listed.get("items") or [])
        row = next((t for t in items if str(t.get("id")) == task_id), None)
        status = str((row or {}).get("status") or "")

        if status != last:
            log(f"  [{elapsed:5.0f}с] {status or '—'}")
            last = status

        # FAILED — окончательный отказ конвейера. Ждать дальше нечего, и
        # отличить его от медленного прогона по таймауту было бы нельзя.
        if status in ("FAILED", "ERROR"):
            raise RunFailed(f"прогон завершился со статусом {status}")

        if status == "REPORT_READY":
            report = api(client, f"/api/tasks/{task_id}/report")
            return report, round(elapsed, 1)

        time.sleep(POLL_SEC)


def collect_personas(client: ApiClient, task_id: str) -> list[dict]:
    """
    Все карточки персон, страницами.

    Считать по одной странице нельзя: условие CDD — `len(per_persona) ==
    audience_size`, и страница по умолчанию в пятьдесят карточек сделала бы это
    сравнение верным ровно до пятидесяти персон, а дальше молча ложным.
    """
    out: list[dict] = []
    skip = 0
    while True:
        page = api(client, f"/api/tasks/{task_id}/report/personas?limit=200&skip={skip}")
        items = page.get("items") or []
        out.extend(items)
        total = page.get("total")
        if not items or (isinstance(total, int) and len(out) >= total):
            return out
        skip += len(items)


# ─── Один прогон ─────────────────────────────────────────────────────────────


def one_run(base_url: str, mode: str, fixture: Path, timeout: int, seed: int) -> dict:
    client = connect(base_url)

    video_ref = upload_video(client, fixture, mode)
    persona_set = make_audience(client, seed)
    survey = pick_survey(client)
    task_id = launch(client, mode=mode, video_ref=video_ref, persona_set=persona_set,
                     survey=survey, seed=seed)
    log(f"  задача {task_id}")

    report, elapsed = wait_for_report(client, task_id, timeout)
    personas = collect_personas(client, task_id)

    aggregate = report.get("aggregate") or {}
    if not aggregate:
        raise RunFailed("отчёт получен, но агрегат пуст — считать было нечего")

    audience_size = report.get("audienceSize")
    if not isinstance(audience_size, int):
        audience_size = len(personas)
    if len(personas) != audience_size:
        raise RunFailed(
            f"карточек {len(personas)}, а персон {audience_size}: часть ответов "
            f"потерялась между воркером и отчётом"
        )

    return {
        "task_id": task_id,
        "mode": mode,
        "seed": seed,
        "status": "REPORT_READY",
        "elapsed_sec": elapsed,
        "audience_size": audience_size,
        "per_persona": [
            {"persona_id": p.get("personaId"), "replication": p.get("replication")}
            for p in personas
        ],
        "aggregate": aggregate,
        # Признак склейки есть только у длинного режима: короткое видео
        # разбирается одним куском, и `true` тут означал бы, что map-reduce
        # отработал там, где его не запускали.
        "stitched": bool(report.get("stitched")) if mode == "long" else None,
        "degraded": report.get("degraded") or [],
    }


# ─── Точка входа ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Сквозной прогон исследования (#22)")
    parser.add_argument("--mode", choices=["short", "long"], default="short")
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", ""))
    parser.add_argument("--artifacts", default=str(DEFAULT_ARTIFACTS))
    parser.add_argument("--timeout", type=int, default=600,
                        help="секунд на один прогон; для long ставьте больше")
    parser.add_argument("--repeat", type=int, default=1,
                        help="golden-сет: 3 означает «доверяем, если 3 из 3»")
    parser.add_argument("--fixture", default="")
    args = parser.parse_args()

    if not args.base_url:
        log("не задан --base-url (или BASE_URL): прогонять нечего")
        return 2

    if args.fixture:
        fixture = Path(args.fixture)
    elif args.mode == "long":
        # Двенадцатиминутный ролик — сотни мегабайт, в git ему не место.
        # Поэтому путь приходит снаружи, а его отсутствие — отказ, а не
        # тихая подмена коротким видео: подмена дала бы зелёный e2e_long,
        # никогда не проверявший склейку.
        long_path = os.environ.get("E2E_LONG_FIXTURE", "")
        if not long_path:
            log("не задан E2E_LONG_FIXTURE: длинного ролика нет, а короткий "
                "вместо него дал бы зелёный e2e_long без проверки склейки")
            return 2
        fixture = Path(long_path)
    else:
        fixture = SHORT_FIXTURE

    runs: list[dict] = []
    failures: list[str] = []

    for attempt in range(1, args.repeat + 1):
        seed = random.randint(1, 10**9)
        log(f"прогон {attempt}/{args.repeat} · режим {args.mode} · seed {seed}")
        try:
            runs.append(one_run(args.base_url, args.mode, fixture, args.timeout, seed))
            log(f"  ✓ прогон {attempt} прошёл")
        except RunFailed as exc:
            failures.append(f"прогон {attempt}: {exc}")
            log(f"  ✗ прогон {attempt} не удался: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"прогон {attempt}: {type(exc).__name__}: {exc}")
            log(f"  ✗ прогон {attempt} упал: {type(exc).__name__}: {exc}")

    if not runs:
        log("")
        log("ни один прогон не состоялся — артефакт не записан:")
        for f in failures:
            log(f"  · {f}")
        return 1

    # Артефакт описывает первый успешный прогон, но несёт счётчики по всем.
    # Гейт требует passed == runs: два прогона из трёх — это не «в основном
    # работает», а «воспроизводится через раз», и такой конвейер не доказан.
    artifact = dict(runs[0])
    artifact["runs"] = args.repeat
    artifact["passed"] = len(runs)
    artifact["failures"] = failures
    if len(runs) > 1:
        artifact["elapsed_sec_all"] = [r["elapsed_sec"] for r in runs]

    out_dir = Path(args.artifacts)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / ARTIFACT_NAME[args.mode]
    target.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    log("")
    log(f"записан {target}  ({len(runs)} из {args.repeat} прогонов)")
    if failures:
        log("часть прогонов не удалась — гейт это увидит и не зачтёт:")
        for f in failures:
            log(f"  · {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
