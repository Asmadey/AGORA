#!/usr/bin/env python3
"""
AGORA loop verifier (skeleton).

External, deterministic verifier for the /goal loop. Runs each acceptance check,
prints a JSON metrics report + human table, writes evals/last_report.json.

Exit code:
  0  -> ALL required checks == pass  (loop green -> Exit A)
  1  -> any required check == fail OR skip (not green yet -> keep looping / Exit B)

Design: stdlib-only, so it runs anywhere with `python evals/check.py`.
Each check returns a dict: {name, status(pass|fail|skip), required, threshold, actual, detail}.
Checks whose subsystem is not built yet return `skip` with a clear reason — that is
the honest state at pass 0 and keeps the loop from going green prematurely.

Config via env:
  AGORA_DATASET   path to unified_respondent_sessions.json (grounding corpus)
  AGORA_MODE      DRY_RUN | CANARY | LIVE  (default DRY_RUN)
"""
from __future__ import annotations
import json, os, re, shutil, sys, subprocess, statistics
from pathlib import Path

EVALS = Path(__file__).resolve().parent
REPO = EVALS.parent                       # корень монорепо (после задачи #1)
WEB = REPO / "apps" / "web"               # Next.js
CORE = REPO / "services" / "agent-core"   # FastAPI + Celery + LangGraph
COMPOSE = REPO / "infra" / "docker-compose.yml"
MODE = os.environ.get("AGORA_MODE", "DRY_RUN")

DATASET = Path(os.environ.get("AGORA_DATASET",
              REPO / "data" / "grounding" / "unified_respondent_sessions.json"))
TASKS = EVALS / "state" / "tasks.json"
ART = EVALS / "artifacts"
# ВАЖНО (решение по persona_grounding): артефакт должен быть получен на ЭТАЛОННОМ
# (reference) конфиге генерации — «сгенерируй как в корпусе», без пользовательских
# фильтров по соцдему. Пользовательские прогоны с произвольным составом аудитории
# (напр. «только 18-24») от проверки распределений освобождены — иначе продуктовый
# сценарий выбора аудитории противоречил бы порогу. Калибровка баллов
# (|mean_gen - mean_real| <= 1.0) действует всегда.
GEN_PERSONAS = ART / "generated_personas.json"      # produced by Persona Generator (reference config)
PERSONA_ANSWERS = ART / "persona_answers.json"       # produced by Respondent agents
E2E_SHORT = ART / "e2e_short_report.json"            # produced by short-video E2E run
E2E_LONG = ART / "e2e_long_report.json"              # produced by long-video E2E run

TOTAL_TASKS = 31   # граф задач: 27 базовых (Ф0–Ф5) + 4 фичи Ф4 (чат, шеринг, перезапуск, файл контекста)
GROUNDING_PROP_TOL = 0.10   # |gen - real| proportion tolerance
GROUNDING_MEAN_TOL = 1.0    # |gen - real| score-mean tolerance (1..10)

AGE_GROUPS = ["14-17", "18-24", "25-34", "35-44", "45-59", "60+"]
GEOS = ["столицы", "центры субъектов", "иные НП"]
GENDERS = ["муж", "жен"]
CRITERIA = ["overall_impression", "plot", "acting", "music", "cinematography"]


def _res(name, status, required=True, threshold=None, actual=None, detail=""):
    return {"name": name, "status": status, "required": required,
            "threshold": threshold, "actual": actual, "detail": detail}


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------- reference distributions from the real grounding corpus ----------

def _proportions(values, buckets):
    n = sum(1 for v in values if v in buckets)
    if n == 0:
        return {b: 0.0 for b in buckets}
    from collections import Counter
    c = Counter(v for v in values if v in buckets)
    return {b: c.get(b, 0) / n for b in buckets}


def real_reference():
    data = _load_json(DATASET)
    if not isinstance(data, list) or not data:
        return None
    socio = [r.get("socio_demographics", {}) or {} for r in data]
    ref = {
        "n": len(data),
        "age_group": _proportions([s.get("age_group") for s in socio], AGE_GROUPS),
        "geo": _proportions([s.get("geo") for s in socio], GEOS),
        "gender": _proportions([s.get("gender") for s in socio], GENDERS),
        "score_means": {},
    }
    for crit in CRITERIA:
        xs = [(_r.get("agora_core_scores_1_to_10", {}) or {}).get(crit) for _r in data]
        xs = [x for x in xs if isinstance(x, (int, float))]
        ref["score_means"][crit] = round(statistics.mean(xs), 2) if xs else None
    return ref


# ---------- checks ----------

def check_tasks_done():
    tasks = _load_json(TASKS)
    if not isinstance(tasks, list):
        return _res("tasks_done", "skip", threshold=f"{TOTAL_TASKS}/{TOTAL_TASKS} done",
                    detail=f"{TASKS} not found or invalid")
    done = sum(1 for t in tasks if str(t.get("status")).lower() == "done")
    total = len(tasks) or TOTAL_TASKS
    ok = done == total and total == TOTAL_TASKS
    return _res("tasks_done", "pass" if ok else "fail",
                threshold=f"{TOTAL_TASKS}/{TOTAL_TASKS}", actual=f"{done}/{total}")


def check_secret_scan():
    # ⚠️ ОБЛАСТЬ: сканируется только REPO. Файлы уровнем выше (напр. AGORA/env.env
    # с живым ключом) сюда не попадают. После реструктуризации в монорепо (задача #1)
    # REPO становится корнем репозитория и покрывает всё, что уедет в git.
    #
    # Расширено 01.08.2026. Прежняя редакция смотрела только код (.ts/.js/.py/.env)
    # и знала два шаблона — sk-… и AIza…. Мимо неё прошла выгрузка рабочего чата в
    # docs/ с root-паролем VPS, паролем managed-инстанса в строке подключения и
    # паролями учётных записей приложения: .md не сканировался, пароль в DSN не
    # распознавался. Зелёная метрика при живом пароле в дереве хуже, чем её отсутствие.
    # Границы слова у sk- обязательны: без них «task-command-router» в любом
    # манифесте читается как ключ OpenAI и метрика краснеет на ровном месте.
    # Ложное срабатывание опаснее, чем кажется: гейт, который врёт, начинают
    # игнорировать, и он перестаёт ловить настоящее.
    pat = re.compile(
        r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{16,}"          # OpenAI-совместимые ключи
        r"|(?<![A-Za-z0-9])AIza[0-9A-Za-z_\-]{20,}"     # Google
        r"|(?<![A-Za-z0-9])hf_[A-Za-z0-9]{20,}"         # Hugging Face
        r"|(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9\-]{10,}"   # Slack
        r"|(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}"      # GitHub
        r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"          # приватные ключи
        # Пароль внутри строки подключения. Ссылка на переменную окружения
        # (${VAR} или $VAR) паролем не является — это как раз правильный способ.
        r"|(?:postgresql|postgres|mongodb(?:\+srv)?|redis|amqp)://[^\s:/@]+:"
        r"(?!\$)[^\s@$]{6,}@"
    )
    # Только для кода: в документации это слово встречается как описание давнего
    # дефекта, а не как сам дефект.
    code_pat = re.compile(r"dangerouslyAllowBrowser")
    # Плейсхолдеры в примерах и документации — не утечка. Список намеренно короткий:
    # чем он длиннее, тем проще спрятать в нём настоящий секрет.
    placeholder = re.compile(
        r"CHANGE_ME|ПАРОЛЬ|сгенерируйте|your-|example|placeholder|xxx+|\*{3,}|…|<[^>]+>",
        re.IGNORECASE,
    )
    skip_dirs = {"node_modules", ".venv", ".git", ".next", "dist", "build", "__pycache__",
                 "fixtures", "grounding", "artifacts", "evals"}
    code_exts = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".env", ".yml", ".yaml")
    # .md/.sql/.sh/.txt/.json добавлены: выгрузки переписки, дампы и отчёты живут
    # именно там, а секрет в них ничем не безопаснее секрета в коде.
    doc_exts = (".md", ".sql", ".sh", ".txt", ".json", ".toml")
    hits = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            is_code = f.endswith(code_exts)
            if not is_code and not f.endswith(doc_exts):
                continue
            if f in (".env.example", "package-lock.json"):
                continue
            p = Path(root) / f
            try:
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if placeholder.search(line):
                        continue
                    if pat.search(line) or (is_code and code_pat.search(line)):
                        hits.append(f"{p.relative_to(REPO)}:{i}")
            except Exception:
                pass
    return _res("secret_scan", "pass" if not hits else "fail",
                threshold="0", actual=str(len(hits)), detail="; ".join(hits[:10]))


def check_persona_grounding():
    ref = real_reference()
    if ref is None:
        return _res("persona_grounding", "skip", threshold=f"|gen-real|≤{GROUNDING_PROP_TOL}",
                    detail=f"grounding dataset not found at {DATASET}")
    gen = _load_json(GEN_PERSONAS)
    if not isinstance(gen, list) or not gen:
        return _res("persona_grounding", "skip", threshold=f"|gen-real|≤{GROUNDING_PROP_TOL}",
                    detail=f"no generated personas at {GEN_PERSONAS} (Persona Generator not run)")
    socio = [(p.get("socio_demographics") or p.get("socio") or {}) for p in gen]
    fails = []
    for dim, buckets in (("age_group", AGE_GROUPS), ("geo", GEOS), ("gender", GENDERS)):
        gp = _proportions([s.get(dim) for s in socio], buckets)
        for b in buckets:
            d = abs(gp[b] - ref[dim][b])
            if d > GROUNDING_PROP_TOL:
                fails.append(f"{dim}:{b} Δ={d:.2f}")
    # score-mean calibration if answers artifact present
    ans = _load_json(PERSONA_ANSWERS)
    if isinstance(ans, list) and ans:
        for crit in CRITERIA:
            xs = [(a.get("scores", {}) or {}).get(crit) for a in ans]
            xs = [x for x in xs if isinstance(x, (int, float))]
            rm = ref["score_means"].get(crit)
            if xs and rm is not None and abs(statistics.mean(xs) - rm) > GROUNDING_MEAN_TOL:
                fails.append(f"score:{crit} Δ={abs(statistics.mean(xs)-rm):.2f}")
    return _res("persona_grounding", "pass" if not fails else "fail",
                threshold=f"prop≤{GROUNDING_PROP_TOL},mean≤{GROUNDING_MEAN_TOL}",
                actual="ok" if not fails else f"{len(fails)} devs", detail="; ".join(fails[:8]))


def _npm_build():
    if not (WEB / "package.json").exists():
        return _res("build_frontend", "skip", detail="apps/web/package.json not found")
    if not (REPO / "node_modules").exists() and not (WEB / "node_modules").exists():
        return _res("build_frontend", "skip", detail="node_modules not installed (npm ci)")
    try:
        # Сборка через workspace-скрипт корня — так Next видит корректный
        # outputFileTracingRoot и тянет общие зависимости монорепо.
        r = subprocess.run(["npm", "run", "build"], cwd=REPO, capture_output=True,
                           text=True, timeout=900)
        return _res("build_frontend", "pass" if r.returncode == 0 else "fail",
                    threshold="exit 0", actual=f"exit {r.returncode}",
                    detail=(r.stderr or "")[-300:] if r.returncode else "")
    except Exception as e:
        return _res("build_frontend", "fail", detail=str(e)[:200])


def _worker_build():
    if not CORE.exists():
        return _res("build_worker", "skip", detail="services/agent-core not present")
    try:
        # pytest + ruff — оба обязательны для green (цель build_worker в /goal).
        env = {**os.environ, "PYTHONPATH": str(CORE)}
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=CORE,
                           capture_output=True, text=True, timeout=900, env=env)
        if r.returncode != 0:
            return _res("build_worker", "fail", threshold="pytest+ruff exit 0",
                        actual=f"pytest exit {r.returncode}",
                        detail=(r.stdout or "")[-300:])
        lint = subprocess.run([sys.executable, "-m", "ruff", "check", "."], cwd=CORE,
                              capture_output=True, text=True, timeout=300, env=env)
        if lint.returncode not in (0, 1):
            # ruff не установлен — тесты прошли, но контракт неполон.
            return _res("build_worker", "skip", threshold="pytest+ruff exit 0",
                        actual="pytest ok, ruff missing", detail="pip install ruff")
        return _res("build_worker", "pass" if lint.returncode == 0 else "fail",
                    threshold="pytest+ruff exit 0",
                    actual="ok" if lint.returncode == 0 else "ruff findings",
                    detail=(lint.stdout or "")[-300:] if lint.returncode else "")
    except Exception as e:
        return _res("build_worker", "fail", detail=str(e)[:200])


def check_compose_health():
    """Поднят ли стек и здоровы ли все сервисы.

    Требует запущенного docker-демона, поэтому в среде без docker честно даёт skip,
    а не выдумывает результат. Реальный вердикт выносится в среде пользователя.
    """
    if not COMPOSE.exists():
        return _res("compose_health", "skip", detail="infra/docker-compose.yml not found")
    if not shutil.which("docker"):
        return _res("compose_health", "skip", detail="docker CLI unavailable in this env")
    # docker-compose.yml объявляет обязательные переменные через ${VAR:?...}, и без
    # файла окружения `docker compose config` падает на первой же из них. Скрипт
    # `npm run up` передаёт --env-file .env.local, а эта проверка — не передавала,
    # поэтому метрика была недостижима на любой машине с установленным docker:
    # «invalid config: required variable … is missing a value». Выглядело как дефект
    # compose, хотя compose был в порядке.
    env_file = REPO / ".env.local"
    base = ["docker", "compose", "-f", str(COMPOSE)]
    if env_file.is_file():
        base += ["--env-file", str(env_file)]

    try:
        cfg = subprocess.run(base + ["config", "--quiet"],
                             cwd=REPO, capture_output=True, text=True, timeout=120)
        if cfg.returncode != 0:
            hint = "" if env_file.is_file() else " (нет .env.local — переменные compose не заданы)"
            return _res("compose_health", "fail", threshold="config valid + all healthy",
                        actual="invalid config", detail=((cfg.stderr or "")[-200:] + hint))
        ps = subprocess.run(base + ["ps", "--format", "json"], cwd=REPO,
                            capture_output=True, text=True, timeout=120)
        if ps.returncode != 0 or not (ps.stdout or "").strip():
            return _res("compose_health", "fail", threshold="all healthy",
                        actual="stack not running", detail="docker compose up -d")
        rows = []
        for line in ps.stdout.splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        unhealthy = [r.get("Service") for r in rows
                     if "healthy" not in str(r.get("Health", "")).lower()
                     and str(r.get("State", "")).lower() != "running"]
        return _res("compose_health", "pass" if rows and not unhealthy else "fail",
                    threshold="all healthy", actual=f"{len(rows) - len(unhealthy)}/{len(rows)}",
                    detail=", ".join(str(u) for u in unhealthy[:5]))
    except Exception as e:
        return _res("compose_health", "fail", detail=str(e)[:200])


def _artifact_pass(name, path, checker):
    art = _load_json(path)
    if art is None:
        return _res(name, "skip", detail=f"{path.name} not produced yet")
    ok, detail = checker(art)
    return _res(name, "pass" if ok else "fail", actual=detail, detail=detail)


def check_e2e_short():
    def chk(a):
        agg = a.get("aggregate"); pp = a.get("per_persona") or []
        ok = bool(agg) and len(pp) == a.get("audience_size", len(pp)) and a.get("status") == "REPORT_READY"
        return ok, f"status={a.get('status')} personas={len(pp)}"
    return _artifact_pass("e2e_short", E2E_SHORT, chk)


def check_e2e_long():
    def chk(a):
        ok = a.get("status") == "REPORT_READY" and a.get("mode") == "long" and bool(a.get("stitched"))
        return ok, f"status={a.get('status')} stitched={a.get('stitched')}"
    return _artifact_pass("e2e_long", E2E_LONG, chk)


def check_rls_tenant():
    """Кросс-арендаторная изоляция: запрос из-под tenant A к строкам B → 0 строк.

    Это ЕДИНСТВЕННАЯ честная проверка RLS — статический разбор SQL показывает, что
    политики написаны, но не что они работают. Требует живого Postgres; без него
    честно skip, а не выдуманный pass.
    """
    init_dir = REPO / "infra" / "postgres" / "init"
    if not (init_dir / "03_rls.sql").exists():
        return _res("rls_tenant", "skip", detail="миграции RLS ещё не написаны (задача #2)")

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return _res("rls_tenant", "skip", threshold="cross-tenant rows == 0",
                    detail="DATABASE_URL не задан — поднимите compose")
    try:
        import psycopg
    except ImportError:
        return _res("rls_tenant", "skip", threshold="cross-tenant rows == 0",
                    detail="psycopg не установлен: pip install 'psycopg[binary]'")

    import uuid as _uuid
    tenant_a, tenant_b = _uuid.uuid4(), _uuid.uuid4()
    try:
        with psycopg.connect(dsn, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL ROLE agora_app")
                for t, nm in ((tenant_a, "verif-a"), (tenant_b, "verif-b")):
                    cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(t),))
                    cur.execute("INSERT INTO teams (id, name) VALUES (%s, %s)", (t, nm))
                    cur.execute("INSERT INTO projects (tenant_id, name) VALUES (%s, %s)",
                                (t, f"p-{nm}"))
                    cur.execute("INSERT INTO surveys (tenant_id, name) VALUES (%s, %s)",
                                (t, f"s-{nm}"))

                problems = []
                # 1. Из-под A строки B не видны нигде.
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_a),))
                for table in ("projects", "surveys", "teams"):
                    col = "id" if table == "teams" else "tenant_id"
                    cur.execute(f"SELECT count(*) FROM {table} WHERE {col} = %s", (tenant_b,))
                    n = cur.fetchone()[0]
                    if n:
                        problems.append(f"{table}: {n} строк B видны из-под A")

                # 2. Без контекста не видно ничего (default deny).
                cur.execute("SELECT set_config('app.tenant_id', '', true)")
                cur.execute("SELECT count(*) FROM projects")
                if (n := cur.fetchone()[0]):
                    problems.append(f"без контекста видно {n} строк")

                # 3. Записать строку чужому арендатору нельзя (WITH CHECK).
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_a),))
                try:
                    cur.execute("SAVEPOINT sp_cross")
                    cur.execute("INSERT INTO projects (tenant_id, name) VALUES (%s, %s)",
                                (tenant_b, "injected"))
                    problems.append("удалось записать строку чужому арендатору")
                    cur.execute("ROLLBACK TO SAVEPOINT sp_cross")
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_cross")

            conn.rollback()  # верификатор не оставляет следов в базе
        return _res("rls_tenant", "pass" if not problems else "fail",
                    threshold="cross-tenant rows == 0",
                    actual="0" if not problems else f"{len(problems)} нарушений",
                    detail="; ".join(problems[:5]))
    except Exception as e:
        return _res("rls_tenant", "fail", threshold="cross-tenant rows == 0",
                    detail=f"{type(e).__name__}: {str(e)[:180]}")


def check_schema_drift():
    """Расхождение между миграциями и живой базой.

    Сравнивает фактическое состояние (relrowsecurity, relforcerowsecurity,
    pg_policies, атрибуты ролей rolsuper/rolbypassrls) с тем, что следует
    из миграций. Расхождение — красная метрика.

    Что проверяется:
    1. FORCE RLS на всех таблицах, где миграции его объявляют (03_rls.sql).
    2. agora_login НЕ имеет BYPASSRLS (01_extensions.sql, AGENTS.md §5).
    3. Количество политик соответствует ожидаемому из миграций.
    4. Нет «призраков» — политик, которых нет в миграциях (заведены руками).

    Без живой базы — честно skip.
    """
    init_dir = REPO / "infra" / "postgres" / "init"
    if not (init_dir / "03_rls.sql").exists():
        return _res("schema_drift", "skip", detail="миграции RLS ещё не написаны (задача #2)")

    dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_ADMIN_URL")
    if not dsn:
        return _res("schema_drift", "skip", threshold="0 drifts",
                    detail="DATABASE_URL не задан — нет подключения к живой базе")
    try:
        import psycopg
    except ImportError:
        return _res("schema_drift", "skip", threshold="0 drifts",
                    detail="psycopg не установлен: pip install 'psycopg[binary]'")

    # Ожидаемое множество таблиц с FORCE RLS — парсим 03_rls.sql.
    rls_sql = (init_dir / "03_rls.sql").read_text(encoding="utf-8", errors="ignore")
    expected_force_tables = set(re.findall(
        r"ALTER\s+TABLE\s+(\w+)\s+FORCE\s+ROW\s+LEVEL\s+SECURITY", rls_sql, re.IGNORECASE
    ))

    # Ожидаемое количество политик — парсим все миграции.
    expected_policy_count = 0
    for sql_file in sorted(init_dir.glob("*.sql")):
        text = sql_file.read_text(encoding="utf-8", errors="ignore")
        # CREATE POLICY ... ON <table> — считаем уникальные (table, policy_name).
        expected_policy_count += len(re.findall(
            r"CREATE\s+POLICY\s+\w+\s+ON\s+\w+", text, re.IGNORECASE
        ))

    drifts = []
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                # 1. FORCE RLS: все ли таблицы из 03_rls.sql имеют force=true?
                cur.execute("""
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind = 'r'
                      AND c.relrowsecurity = true
                    ORDER BY c.relname
                """)
                actual_rls = {r[0]: {"rls": r[1], "force": r[2]} for r in cur.fetchall()}

                for tbl in sorted(expected_force_tables):
                    info = actual_rls.get(tbl)
                    if not info:
                        drifts.append(f"таблица {tbl} — нет в базе (миграция не применена?)")
                    elif not info["force"]:
                        drifts.append(f"таблица {tbl} — FORCE RLS снят (ожидается ON)")

                # 2. agora_login не должен иметь BYPASSRLS.
                cur.execute("""
                    SELECT rolname, rolbypassrls, rolsuper
                    FROM pg_roles
                    WHERE rolname IN ('agora_login', 'agora_app', 'agora_share_login')
                    ORDER BY rolname
                """)
                for rname, bypass, sup in cur.fetchall():
                    if bypass:
                        drifts.append(f"роль {rname} имеет BYPASSRLS — нарушение AGENTS.md §5")
                    if sup and rname != "agora":
                        drifts.append(f"роль {rname} — суперпользователь (неожиданно)")

                # 3. Количество политик.
                cur.execute("""
                    SELECT count(*) FROM pg_policies WHERE schemaname = 'public'
                """)
                actual_policies = cur.fetchone()[0]
                if actual_policies != expected_policy_count:
                    drifts.append(
                        f"политик: {actual_policies} в базе vs {expected_policy_count} в миграциях"
                    )

                # 4. Призраки: политики, которых нет ни в одной миграции.
                cur.execute("""
                    SELECT policyname FROM pg_policies WHERE schemaname = 'public'
                    ORDER BY policyname
                """)
                actual_policy_names = {r[0] for r in cur.fetchall()}

                expected_policy_names = set()
                for sql_file in sorted(init_dir.glob("*.sql")):
                    text = sql_file.read_text(encoding="utf-8", errors="ignore")
                    expected_policy_names.update(
                        m.group(1)
                        for m in re.finditer(
                            r"CREATE\s+POLICY\s+(\w+)\s+ON", text, re.IGNORECASE
                        )
                    )

                ghosts = actual_policy_names - expected_policy_names
                if ghosts:
                    drifts.append(f"политики-призраки (нет в миграциях): {', '.join(sorted(ghosts))}")

        return _res("schema_drift", "pass" if not drifts else "fail",
                    threshold="0 drifts",
                    actual="0" if not drifts else f"{len(drifts)} drifts",
                    detail="; ".join(drifts[:8]))
    except Exception as e:
        return _res("schema_drift", "fail", threshold="0 drifts",
                    detail=f"{type(e).__name__}: {str(e)[:180]}")


def _todo(name):
    return _res(name, "skip", detail="subsystem not implemented yet")


def check_prompts_editable():
    """Метрика prompts_editable (задача #26).

    Проверяет, что правка промпта у арендатора меняет то, что уходит в модель,
    и не задевает другого арендатора. Без живой базы — честно skip.

    Поведенческая проверка: два арендатора, у одного — своя версия, у второго
    дефолт. Резолвер отдаёт каждому свою версию. Без БД проверяется только
    наличие файлов: миграции, резолвера и API-роутов.
    """
    init_dir = REPO / "infra" / "postgres" / "init"
    if not (init_dir / "07_prompts_seed.sql").exists():
        return _res("prompts_editable", "skip",
                    detail="07_prompts_seed.sql ещё не сгенерирован (задача #26)")

    # Статическая проверка: резолвер использует ORDER BY tenant_id NULLS LAST
    resolver = WEB / "lib" / "server" / "prompts.ts"
    if not resolver.exists():
        return _res("prompts_editable", "skip",
                    detail="apps/web/lib/server/prompts.ts не найден (задача #26)")
    src = resolver.read_text(encoding="utf-8", errors="ignore")
    if "ORDER BY tenant_id NULLS LAST" not in src:
        return _res("prompts_editable", "fail",
                    threshold="ORDER BY tenant_id NULLS LAST",
                    actual="не найдено в резолвере",
                    detail="резолвер должен использовать один запрос с ORDER BY tenant_id NULLS LAST")

    # API-роуты существуют
    api_dir = WEB / "app" / "api" / "prompts"
    required_routes = [
        api_dir / "route.ts",
        api_dir / "[key]" / "route.ts",
        api_dir / "[key]" / "activate" / "route.ts",
        api_dir / "[key]" / "preview" / "route.ts",
    ]
    missing_routes = [str(p.relative_to(WEB)) for p in required_routes if not p.exists()]
    if missing_routes:
        return _res("prompts_editable", "skip",
                    detail=f"API-роуты не найдены: {', '.join(missing_routes)}")

    # Поведенческая проверка требует живой БД
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return _res("prompts_editable", "skip",
                    threshold="cross-tenant prompt isolation",
                    detail="DATABASE_URL не задан — проверка требует живой Postgres")
    try:
        import psycopg
    except ImportError:
        return _res("prompts_editable", "skip",
                    threshold="cross-tenant prompt isolation",
                    detail="psycopg не установлен: pip install 'psycopg[binary]'")

    import uuid as _uuid
    tenant_a, tenant_b = _uuid.uuid4(), _uuid.uuid4()
    test_key = "qa.grounding"  # один из 13 засеянных ключей
    test_marker = f"TEST_MARKER_{_uuid.uuid4().hex[:8]}"

    try:
        with psycopg.connect(dsn, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL ROLE agora_app")

                # Создаём двух арендаторов
                for t, nm in ((tenant_a, "prompt-verif-a"), (tenant_b, "prompt-verif-b")):
                    cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(t),))
                    cur.execute("INSERT INTO teams (id, name) VALUES (%s, %s)", (t, nm))

                # Арендатор A сохраняет свою версию промпта с маркером
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_a),))
                cur.execute(
                    "INSERT INTO prompts (tenant_id, key, stage, template, variables, "
                    "model_params, version, is_active, is_default) "
                    "VALUES (%s, %s, (SELECT stage FROM prompts WHERE key = %s LIMIT 1), "
                    "%s, '[]'::jsonb, '{}'::jsonb, 2, true, false)",
                    (tenant_a, test_key, test_key, test_marker),
                )

                # Арендатор A видит свою версию (с маркером)
                cur.execute(
                    "SELECT template FROM prompts WHERE key = %s AND is_active = true "
                    "ORDER BY tenant_id NULLS LAST LIMIT 1",
                    (test_key,),
                )
                a_template = cur.fetchone()[0]
                if test_marker not in a_template:
                    return _res("prompts_editable", "fail",
                                threshold="арендатор A видит свою версию",
                                actual="маркер не найден в резолве A",
                                detail=f"ожидался маркер {test_marker}")

                # Арендатор B видит дефолт (без маркера)
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_b),))
                cur.execute(
                    "SELECT template FROM prompts WHERE key = %s AND is_active = true "
                    "ORDER BY tenant_id NULLS LAST LIMIT 1",
                    (test_key,),
                )
                b_template = cur.fetchone()[0]
                if test_marker in b_template:
                    return _res("prompts_editable", "fail",
                                threshold="арендатор B видит дефолт, а не версию A",
                                actual="маркер A найден в резолве B",
                                detail="правка A утекла в B — изоляция нарушена")

            conn.rollback()

        return _res("prompts_editable", "pass",
                    threshold="cross-tenant prompt isolation",
                    actual="A видит свою, B — дефолт",
                    detail="изоляция версий промптов работает")
    except Exception as e:
        return _res("prompts_editable", "fail",
                    threshold="cross-tenant prompt isolation",
                    detail=f"{type(e).__name__}: {str(e)[:180]}")


CHECKS = [
    check_tasks_done,
    _npm_build,
    _worker_build,
    check_compose_health,
    check_e2e_short,
    check_e2e_long,
    lambda: _todo("isolation_persona"),
    check_rls_tenant,
    check_schema_drift,
    check_persona_grounding,
    lambda: _todo("response_diversity"),
    lambda: _todo("qa_catches_injected"),
    check_prompts_editable,
    check_secret_scan,
    lambda: _todo("subjective_persona_realism"),   # external LLM grader, blind, ≥7/10
    lambda: _todo("subjective_report_quality"),     # external LLM grader, blind, ≥7/10
]


def main():
    results = []
    for c in CHECKS:
        try:
            results.append(c())
        except Exception as e:
            results.append(_res(getattr(c, "__name__", "check"), "fail", detail=f"exception: {e}"))

    required_fail = [r for r in results if r["required"] and r["status"] in ("fail", "skip")]
    green = len(required_fail) == 0
    report = {"mode": MODE, "green": green,
              "summary": {"pass": sum(r["status"] == "pass" for r in results),
                          "fail": sum(r["status"] == "fail" for r in results),
                          "skip": sum(r["status"] == "skip" for r in results),
                          "total": len(results)},
              "results": results}
    (EVALS / "last_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                            encoding="utf-8")

    # human table on stderr
    icon = {"pass": "✅", "fail": "❌", "skip": "⏭️"}
    print(f"AGORA verifier — mode={MODE}  green={green}", file=sys.stderr)
    for r in results:
        print(f"  {icon.get(r['status'],'?')} {r['name']:<28} "
              f"thr={r['threshold'] or '-'!s:<22} act={r['actual'] or '-'!s:<10} {r['detail'][:60]}",
              file=sys.stderr)
    print(f"  → pass={report['summary']['pass']} fail={report['summary']['fail']} "
          f"skip={report['summary']['skip']}", file=sys.stderr)

    # machine JSON on stdout
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0 if green else 1)


if __name__ == "__main__":
    main()
