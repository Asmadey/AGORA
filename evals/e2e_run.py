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

#: Сколько ждать наполнения набора персон.
#:
#: Генерация ушла в воркер и стала фоновой: маршрут отвечает 202, а персон пишет
#: Celery-задача. Обогащение — последовательный цикл с вызовом модели на каждую
#: персону, поэтому двенадцать персон занимают минуты, а не секунды.
AUDIENCE_TIMEOUT_SEC = 600
AUDIENCE_POLL_SEC = 5

#: Какая доля аудитории обязана пережить QA, чтобы отчёту можно было верить.
#:
#: Две трети — не круглое число ради круглости: при перекрытии 1 и двенадцати
#: персонах это восемь ответов, то есть выборка, на которой посегментный разрез
#: ещё имеет смысл. Ниже — отчёт держится на горстке ответов, оставаясь на вид
#: полноценным.
MIN_SURVIVING_SHARE = 0.67

#: Пауза между опросами статуса. Чаще — лишняя нагрузка на сервер, который в
#: это время считает; реже — прогон дольше своего же таймаута.
POLL_SEC = 5


class RunFailed(RuntimeError):
    """Прогон не состоялся. Текст обязан называть шаг, на котором всё встало."""


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# ─── Шаги прогона ────────────────────────────────────────────────────────────


def _why_unreachable(payload: str, base_url: str) -> str:
    """
    Отличает недоступный сервер от недоверенного сертификата.

    Первая редакция на любой отказ советовала «проверьте BASE_URL». На
    macOS-сборке python.org это неверный совет: адрес правильный, сервер отвечает,
    а Python не пользуется системной связкой корневых сертификатов и не доверяет
    валидному Let's Encrypt. Диагностика, уводящая в сторону, стоит дороже, чем
    её отсутствие: по ней проверяют адрес, находят его верным и остаются без
    объяснения.
    """
    if "CERTIFICATE_VERIFY_FAILED" in payload or "SSL" in payload:
        return (
            f"сертификат {base_url} не проверен. Сам адрес при этом рабочий — "
            f"проверьте curl'ом. Python из python.org на macOS не читает связку "
            f"корневых сертификатов системы; лечится один раз: "
            f"'/Applications/Python 3.13/Install Certificates.command' либо "
            f"pip install --upgrade certifi и "
            f"export SSL_CERT_FILE=$(python3 -m certifi)"
        )
    return f"сервер недоступен ({payload[:160]}). Проверьте BASE_URL={base_url}"


def connect(base_url: str) -> ApiClient:
    client = ApiClient(base_url)

    code, payload = client.call("/api/health")
    if code != 200:
        raise RunFailed(f"GET /api/health вернул {code}: {_why_unreachable(payload, base_url)}")

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


def listing(payload: dict, key: str, endpoint: str) -> list[dict]:
    """
    Массив из ответа-списка. Отсутствие ожидаемого ключа — отказ, а не пустота.

    Первая редакция везде писала `payload.get("items") or []`, а имена ключей
    угадала: `/api/tasks` отдаёт `tasks`, `/api/surveys` — `surveys`. Прогонщик
    получал пустой список, не находил в нём собственную задачу и семьсот секунд
    честно сообщал «последний статус неизвестен», пока та уже упала.

    Отсюда форма проверки. Пустой список законен — прогонов может не быть; но
    ответ БЕЗ ключа означает, что мы читаем не то, что отдают, и продолжать по
    нему нельзя.
    """
    if isinstance(payload, list):
        return payload
    if key not in payload:
        raise RunFailed(
            f"{endpoint} вернул ответ без ключа {key!r} (есть: "
            f"{sorted(payload)[:6]}). Прогонщик и маршрут разошлись в контракте"
        )
    value = payload[key]
    return value if isinstance(value, list) else []


def make_audience(client: ApiClient, seed: int) -> str:
    """
    Набор персон, В КОТОРОМ ЕСТЬ ПЕРСОНЫ.

    Раньше здесь стоял POST /api/persona-sets. Он заводит ЗАПИСЬ о наборе и
    ничего не генерирует, поэтому прогон уходил в работу с пустой аудиторией:
    скачивал ролик, нормализовал, расшифровывал речь, разбирал кадры моделью со
    зрением — и падал на узле опроса с «персоны не загружены». На 363-й секунде,
    уже потратив всё оплаченное.

    Генерация идёт тем же маршрутом, что и шаг визарда: POST /api/audience —
    заземлённый на корпус генератор. Прогонщик обязан ходить теми же дорогами,
    что пользователь, иначе он проверяет не тот путь, которым пойдут люди.

    Пустой ответ — отказ здесь, а не в конвейере: ноль персон в наборе делает
    прогон заведомо провальным, и узнавать об этом через шесть минут незачем.
    """
    made = api(client, "/api/audience", "POST", {
        "size": AUDIENCE_SIZE,
        # Весь диапазон по каждому критерию: контракт отвергает пустой список
        # как незаполненный критерий, а сужать выборку прогонщику незачем.
        "ageGroups": ["14-17", "18-24", "25-34", "35-44", "45-59", "60+"],
        "geos": ["столицы", "центры субъектов"],
        "genders": ["муж", "жен"],
    })
    set_id = made.get("personaSetId") or (made.get("personaSet") or {}).get("id")
    if not set_id:
        raise RunFailed(f"набор персон не создан: {json.dumps(made, ensure_ascii=False)[:200]}")

    # ── Ожидание фоновой генерации ──────────────────────────────────────────
    #
    # Маршрут отвечает 202: набор заведён, персон в нём ещё нет — их пишет
    # воркер. Поле `size` в ответе — это ЗАКАЗАННЫЙ размер, а не готовый, и
    # читать его как готовый было ошибкой прогонщика: он тут же шёл запускать
    # прогон, а запуск отказывал «в наборе нет ни одной персоны». Три прогона
    # подряд не состоялись именно так, причём каждый успел оплатить загрузку
    # ролика.
    #
    # Опрос, а не мгновенная проверка: обогащение — последовательный цикл по
    # персонам с вызовом модели на каждую, и двенадцать персон занимают минуты.
    deadline = time.time() + AUDIENCE_TIMEOUT_SEC
    generated = 0
    status = "generating"
    while time.time() < deadline:
        sets = api(client, "/api/persona-sets", "GET").get("personaSets") or []
        mine = next((s for s in sets if str(s.get("id")) == str(set_id)), None)
        if mine is None:
            raise RunFailed(f"набор {set_id} исчез из списка сразу после создания")
        status = str(mine.get("status") or "")
        generated = int(mine.get("personaCount") or mine.get("generatedCount") or 0)
        if status == "failed":
            raise RunFailed(
                f"генерация набора {set_id} провалилась: {mine.get('error') or 'без причины'}"
            )
        if status == "ready":
            break
        time.sleep(AUDIENCE_POLL_SEC)
    else:
        raise RunFailed(
            f"набор {set_id} не наполнился за {AUDIENCE_TIMEOUT_SEC} с "
            f"(статус {status}, персон {generated}) — смотрите лог воркера"
        )

    if generated == 0:
        raise RunFailed(
            f"набор {set_id} готов, но персон в нём ноль — прогон дошёл бы до "
            f"опроса и упал там"
        )
    log(f"  аудитория {set_id}: {generated} персон")
    return str(set_id)


def pick_survey(client: ApiClient) -> str | None:
    """
    Анкета арендатора, если она есть.

    Отсутствие — не отказ: запуск без анкеты законен, персоны отвечают по пяти
    базовым критериям. Придумывать анкету здесь значило бы проверять конвейер на
    данных, которых в его настоящей работе не бывает.
    """
    for item in listing(api(client, "/api/surveys"), "surveys", "GET /api/surveys"):
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

        rows = listing(api(client, "/api/tasks"), "tasks", "GET /api/tasks")
        row = next((t for t in rows if str(t.get("id")) == task_id), None)
        if row is None:
            # Собственная задача пропала из списка — наблюдать за прогоном
            # больше нечем. Ждать до таймаута значило бы выдать «не уложился»
            # вместо настоящей причины, а она в этот момент уже известна.
            raise RunFailed(
                f"задача {task_id} не найдена среди {len(rows)} прогонов в "
                f"GET /api/tasks: следить за ней нечем"
            )
        status = str(row.get("status") or "")

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
        items = listing(page, "items", "GET /api/tasks/{id}/report/personas")
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

    # ─── На скольких ответах стоит отчёт ─────────────────────────────────────
    #
    # Прежний гейт проверял только равенство карточек и персон и потому засчитал
    # прогон, чей агрегат посчитан по ТРЁМ ответам из одиннадцати: QA забраковал
    # восемь. Отчёт при этом выглядел нормальным отчётом — NPS −100,
    # эмоциональный индекс 10, «100% испытали скепсис». Все три числа честные и
    # все три бессмысленные, а различить это по экрану нечем.
    #
    # Порог именно доля, а не абсолютное число: смысл в том, какую часть
    # аудитории пришлось выбросить. Массовая отбраковка — это либо сломанное
    # правило QA, либо испортившаяся модель, и оба случая обязаны краснеть, а не
    # проезжать под видом успешного прогона.
    sample_size = aggregate.get("sample_size")
    excluded = aggregate.get("excluded_by_qa") or 0
    if isinstance(sample_size, int) and audience_size:
        survived = sample_size / audience_size
        if survived < MIN_SURVIVING_SHARE:
            raise RunFailed(
                f"агрегат посчитан по {sample_size} ответам из {audience_size} "
                f"({survived:.0%}): QA забраковал {excluded}. Отчёт на такой доле "
                f"выглядит полноценным и не является им — смотрите qa_report.json"
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
