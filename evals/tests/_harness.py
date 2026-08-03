"""
Общая обвязка поведенческого уровня CDD-тестов.

Появилась после прохода 9, где живой прогон на VPS показал два дефекта стенда,
из-за которых поведенческий уровень пяти задач никогда не исполнялся, а задачи
при этом стояли `done`:

1. Тесты #8 и #10 ходили в API без сессии и получали 401 на каждом запросе.
   В графе это было записано как «требует S3 creds» и «требует BASE_URL» —
   то есть причина в заметке не совпадала с настоящей.

2. Тесты #2, #3, #4 падали с «failed to resolve host 'postgres'»: в .env.local
   строка подключения указывает на имя сервиса compose, которое резолвится
   только внутри сети контейнеров, а тест исполняется на хосте.

Оба случая — один класс: проверка не отличала «среды нет» от «стенд собран
неверно», и в обоих случаях молчала. Поэтому здесь всё, что нужно для входа и
подключения, лежит в одном месте и одинаково ведёт себя во всех тестах.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

__all__ = ["ApiClient", "login", "db_dsn", "creds"]


# ─── База ────────────────────────────────────────────────────────────────────


def db_dsn(var: str = "DATABASE_URL") -> str | None:
    """
    Строка подключения с хостом, достижимым оттуда, откуда запущен тест.

    В .env.local хост — имя сервиса compose (`postgres`). Внутри сети контейнеров
    оно резолвится, на хосте — нет, а порт наружу проброшен. Раньше это давало
    FAIL с «Temporary failure in name resolution», который читался как поломка
    базы, хотя база была цела.

    Подмена делается только если имя действительно не резолвится: внутри
    контейнера строка обязана остаться нетронутой, иначе тест пойдёт не туда.
    """
    dsn = os.environ.get(var)
    if not dsn:
        return None

    try:
        parsed = urllib.parse.urlsplit(dsn)
        host = parsed.hostname
    except ValueError:
        return dsn
    if not host:
        return dsn

    try:
        socket.getaddrinfo(host, None)
        return dsn  # имя резолвится — не трогаем
    except socket.gaierror:
        pass

    netloc = parsed.netloc.replace(f"@{host}", "@127.0.0.1", 1) if "@" in parsed.netloc \
        else parsed.netloc.replace(host, "127.0.0.1", 1)
    return urllib.parse.urlunsplit(parsed._replace(netloc=netloc))


# ─── Учётные данные ──────────────────────────────────────────────────────────


def creds(role: str = "owner") -> tuple[str | None, str | None]:
    """
    Пара (адрес, пароль) для входа тестового клиента.

    Заводятся скриптом apps/web/scripts/seed-auth.mjs и хранятся в .env.local,
    который под .gitignore. В репозиторий они не попадают и не должны.
    """
    if role == "member":
        return os.environ.get("MEMBER_EMAIL"), os.environ.get("MEMBER_PASSWORD")
    return (
        os.environ.get("CDD_OWNER_EMAIL") or os.environ.get("OWNER_EMAIL"),
        os.environ.get("CDD_OWNER_PASSWORD") or os.environ.get("OWNER_PASSWORD"),
    )


# ─── HTTP-клиент с сессией ───────────────────────────────────────────────────


class ApiClient:
    """
    Клиент к API, умеющий входить так же, как это делает браузер.

    Ошибки HTTP возвращаются кодом, а не исключением: проверке нужно сравнить
    код с ожидаемым, а не упасть трассировкой на первом же 400.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def call(
        self,
        path: str,
        method: str = "GET",
        body: bytes | None = None,
        form: bool = False,
    ) -> tuple[int, str]:
        req = urllib.request.Request(
            self.base_url + path,
            method=method,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
                if form
                else "application/json"
            },
        )
        try:
            with self.opener.open(req, timeout=20) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            # Ноль вместо кода: проверка должна честно упасть с понятным
            # текстом, а не рухнуть трассировкой.
            return 0, f"нет соединения: {e.reason}"

    @property
    def authenticated(self) -> bool:
        return any("session-token" in c.name for c in self.jar)

    def login(self, email: str, password: str) -> tuple[bool, str]:
        """
        Вход через Auth.js Credentials. Возвращает (успех, пояснение).

        Auth.js защищён от CSRF двойной отправкой: токен приходит и в куке, и
        полем формы, поэтому пройти надо тем же путём, что и браузер, —
        сначала /api/auth/csrf, потом callback. Сокращать нельзя: без куки
        колбэк вернёт 302 на форму логина, и это будет выглядеть как успех.
        """
        code, payload = self.call("/api/auth/csrf")
        try:
            csrf = json.loads(payload)["csrfToken"]
        except Exception:  # noqa: BLE001
            return False, f"csrfToken не получен (код {code})"

        form = urllib.parse.urlencode(
            {
                "email": email,
                "password": password,
                "csrfToken": csrf,
                "callbackUrl": self.base_url,
                "json": "true",
            }
        ).encode()
        code, _ = self.call("/api/auth/callback/credentials", "POST", form, form=True)
        if not self.authenticated:
            return False, f"куки сессии не выдана (код {code}); проверьте пароль и членство"
        return True, ""

    def session(self) -> dict:
        code, payload = self.call("/api/auth/session")
        if code != 200:
            return {}
        try:
            return json.loads(payload) or {}
        except Exception:  # noqa: BLE001
            return {}


def login(base_url: str, role: str = "owner") -> tuple[ApiClient | None, str]:
    """
    Готовый клиент с сессией либо причина, по которой его нет.

    Причина возвращается текстом, чтобы вызывающий тест сам решил, SKIP это
    (учётных данных не задали) или FAIL (данные есть, а войти не вышло).
    Разница принципиальная: первое — отсутствие среды, второе — дефект.
    """
    email, password = creds(role)
    if not (email and password):
        env = "MEMBER_EMAIL / MEMBER_PASSWORD" if role == "member" \
            else "CDD_OWNER_EMAIL / CDD_OWNER_PASSWORD"
        return None, (
            f"не заданы {env}; заведите учётную запись "
            f"apps/web/scripts/seed-auth.mjs --team-id <uuid> --role {role}"
        )

    client = ApiClient(base_url)
    ok, why = client.login(email, password)
    if not ok:
        return None, why
    return client, ""
