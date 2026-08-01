# AGORA

**Self-hosted синтетические фокус-группы для оценки видеоконента**

> «Прогноз, а не догадка» — позиционирование продукта: вместо офлайн-фокус-групп (недели и десятки тысяч рублей) AGORA генерирует синтетическую аудиторию из AI-персон, «показывает» им видео и за минуты выдаёт аналитический отчёт.

---

## Содержание

1. [Что такое AGORA](#что-такое-agora)
2. [Архитектура](#архитектура)
3. [Технологический стек](#технологический-стек)
4. [Структура проекта](#структура-проекта)
5. [База данных (RLS, мультиарендность, SECURITY DEFINER)](#база-данных)
6. [Аутентификация](#аутентификация)
7. [Деплой](#деплой)
8. [CDD — тестирование через контракт](#cdd--тестирование)
9. [Текущий статус](#текущий-статус)
10. [Локальный запуск](#локальный-запуск)

---

## Что такое AGORA

**AGORA** — self-hosted платформа для оценки сериалов и роликов до релиза. Офлайн фокус-группа — это недели и десятки тысяч рублей за один показ в одном городе. AGORA генерирует синтетическую аудиторию из AI-персон (цифровых двойников зрителей) по соцдем-параметрам, «показывает» им видео и за минуты выдаёт аналитический отчёт — усреднённо по аудитории и по каждой персоне.

### Ключевые отличия от «спросить у LLM»

1. **Заземление на реальный корпус** — 165 карточек респондентов из реальных фокус-групп
2. **Реальный анализ видео** — транскрипция + диаризация + разбор сцен через VLM
3. **Калибровка оценок** — сверка с реальными распределениями из корпуса
4. **Изоляция ответов** — каждая персона видит только свой профиль и контент видео
5. **QA-верификация** — LLM-as-judge проверяет консистентность, grounding и разнообразие
6. **Периметр РФ / self-host** — резидентность данных, модели через российский API

### Целевая аудитория

Студии, онлайн-кинотеатры, продюсерские центры. MVP — команды ≤10 человек, мультиарендно.

### Основные сценарии

- **Продюсер/шоураннер** — за час получить сводный балл и разбор по сегментам для решения go/no-go до релиза
- **Сценарист/режиссёр** — увидеть проседающие сцены и почему (цитаты + таймкоды) для точечной переработки
- **Маркетинг-аналитик** — посегментные метрики (NPS, ретеншн, эмоции) для позиционирования
- **Research lead** — настраивать аудиторию, анкету и промпты, доверяя заземлению
- **Исследователь** — переиспользовать набор персон на новом ролике для сопоставимости

---

## Архитектура

```
                    ┌─────────────────────────────────────────────────────┐
                    │                    VPS (TimeWeb)                    │
                    │                                                      │
                    │  ┌──────────────┐        ┌──────────────────────┐  │
                    │  │   Nginx      │───────▶│   Next.js 15 (web)   │  │
                    │  │  reverse     │        │   App Router          │  │
                    │  │  proxy +SSL  │        │   Auth.js v5          │  │
                    │  └──────────────┘        │   Standalone build    │  │
                    │                          └──────────┬───────────┘  │
                    │                                     │                │
                    │                          ┌──────────▼───────────┐  │
                    │                          │  FastAPI + Celery    │  │
                    │                          │  + LangGraph worker  │  │
                    │                          │  (agent-core)        │  │
                    │                          └──┬────┬────┬────┬────┘  │
                    │                             │    │    │    │       │
                    │              ┌──────────────┘    │    │    │       │
                    │              ▼                   ▼    │    │       │
                    │  ┌──────────────┐  ┌──────────────┐  │    │       │
                    │  │  PostgreSQL  │  │   MongoDB    │  │    │       │
                    │  │  18 + RLS    │  │   8.0        │  │    │       │
                    │  └──────────────┘  └──────────────┘  │    │       │
                    │                                     ▼    ▼       │
                    │                          ┌──────────┐ ┌────────┐  │
                    │                          │  Valkey  │ │  S3    │  │
                    │                          │  (Redis) │ │ 100 GB │  │
                    │                          └──────────┘ └────────┘  │
                    └─────────────────────────────────────────────────────┘
                                        │
                                        ▼
                          ┌──────────────────────────────┐
                          │  timeweb.cloud API            │
                          │  (Qwen 3.6 — VLM + reasoning) │
                          └──────────────────────────────┘
```

### Бэкенд-пайплайн (LangGraph внутри Celery-задачи)

```
extract_audio
  → [WhisperX ∥ pyannote (полный трек)]
  → merge_transcript
  → route (short | long)
  → sample_frames (PySceneDetect + панели ×4)
  → analyze_chunks (Qwen VLM → JSON, MAP через Send)
  → stitch (REDUCE: video_understanding по таймлайну)
  → evaluate_personas (Qwen, MAP, изоляция; ×replication_count)
  → qa (LLM-as-judge ×2: consistency / grounding / diversity)
  → analytics (агрегат + групповой синтез + доверительные границы)
  → REPORT_READY (прогресс в Valkey → SSE)
```

### Изоляция персон

Каждая персона получает в срезе state **только** свою DNA + `video_understanding` + `survey`. Персона не знает о других персонах и о том, что участвует в исследовании. Guardrail: ответ ограничен задокументированным профилем — вне профиля → «не знаю», а не выдумка.

---

## Технологический стек

| Слой | Технология | Версия |
|------|-----------|--------|
| **Frontend** | Next.js (App Router, standalone build) | 15.4 |
| | React | 19.2 |
| | TypeScript | 5.9 |
| | Tailwind CSS | 4.1 |
| | Auth.js (next-auth) | 5.0 (beta) |
| | Radix UI, Recharts, Motion | — |
| **Backend** | FastAPI + Celery + LangGraph | Python 3.14 |
| | faster-whisper (STT) | large-v3, int8 CPU |
| | pyannote (диаризация) | 3.1 |
| | PySceneDetect (разделение сцен) | — |
| | ffmpeg | — |
| **БД** | PostgreSQL | 18 |
| | MongoDB | 8.0 |
| | Valkey (Redis-compatible) | 9.1 |
| **Хранилище** | S3 (TimeWeb) | 100 GB Standard |
| **LLM** | Qwen 3.6 (мультимодальная) | через timeweb.cloud API |
| **Инфраструктура** | Docker Compose | — |
| | Nginx (reverse proxy + SSL) | — |
| | Let's Encrypt | — |
| **Контракт TS↔Python** | Canonical JSON Schema | — |

---

## Структура проекта

```
AGORA/
├── apps/
│   └── web/                    # Next.js 15 фронтенд (App Router, standalone)
│       ├── app/                # Маршруты: login, projects, personas, runs,
│       │                      #   portraits, prompts, settings, api/*
│       ├── components/         # UI-компоненты
│       └── package.json
├── services/
│   └── agent-core/             # FastAPI + Celery + LangGraph воркер
├── packages/
│   └── shared/                 # Общие типы и JSON Schema
├── infra/
│   ├── docker-compose.yml      # Оркестрация: postgres, mongo, valkey, web, worker
│   ├── postgres/init/          # SQL-миграции (нумерованные, идемпотентные)
│   │   ├── 01_extensions.sql
│   │   ├── 02_schema.sql       # Таблицы
│   │   ├── 03_rls.sql          # Row Level Security
│   │   ├── 04_login_role.sh    # Роль приложения (agora_app)
│   │   ├── 05_auth.sql         # SECURITY DEFINER функции аутентификации
│   │   └── 06_owner_read_auth_tables.sql
│   ├── web.Dockerfile
│   └── worker.Dockerfile
├── evals/
│   ├── check.py                # Внешний верификатор (гейт проекта)
│   ├── state/
│   │   └── tasks.json          # Граф из 31 задачи
│   ├── tests/                  # CDD-тесты по задачам
│   └── fixtures/
├── prompts/                    # 13 seed-промптов (Промпт-студия)
├── data/
│   └── grounding/
│       └── unified_respondent_sessions.json  # Корпус: 165 записей
├── docs/                       # PRD, методология, аудитория, handoff
├── AGENTS.md                   # Протокол работы агентов
└── .env.local                  # Секреты (в .gitignore)
```

---

## База данных

### Мультиарендность

Модель **«команда = арендатор»** (Decision Log #9): `teams.id` используется как `tenant_id` во всех прикладных таблицах. Роли: `owner` / `member`.

### Row Level Security (RLS)

Все прикладные таблицы защищены RLS по `tenant_id`. Три критических правила:

1. **`ENABLE` недостаточно — нужен `FORCE ROW LEVEL SECURITY`.** Без него владелец таблицы обходит политики, а владелец — это роль, под которой идут миграции. `FORCE` не снимается.
2. **Приложение ходит под `agora_app`** (`NOSUPERUSER NOBYPASSRLS`) — никогда под владельцем таблиц.
3. **Незаданный tenant-контекст = пустая выборка** (default deny). `app.current_tenant()` возвращает `NULL`, сравнение с `NULL` не истинно.

Tenant-контекст устанавливается через `set_config('app.tenant_id', $1, true)` (не `SET LOCAL` — `SET` не принимает параметры).

### SECURITY DEFINER

Единственный легальный обход RLS — функции `SECURITY DEFINER` с узким контрактом и фиксированным `search_path`. Используются для аутентификации: при входе порядок обратный обычному (сначала пользователь, потом арендатор), но `team_members` закрыт политикой `team_id = app.current_tenant()`, а контекст ещё пуст. Вместо снятия RLS — две функции с правами владельца, отдающие ровно строки одного пользователя.

### Исключение: публичные ссылки

`report_shares` — единственный санкционированный обход RLS: публичная read-only ссылка с криптостойким токеном ≥128 бит, TTL и revoke. Реализуется отдельной политикой и покрывается негативными тестами (истёкший/отозванный/чужой токен → 410/404).

### Схема

**Postgres (RLS по tenant_id):** `teams`, `users`, `team_members`, `projects`, `personas`, `persona_sets`, `audience_portraits`, `audience_context_files`, `prompts`, `surveys`, `tasks` (+`prompts_snapshot`, +`replication_count`, +`parent_task_id`, +`carry_over_memory`), `reports`, `settings`, `report_shares`, `chat_threads`, `chat_messages`.

**MongoDB:** `chunk_analyses`, `persona_answers`, `wizard_drafts`, `grounding_dataset`.

**S3:** `video/`, `audio/`, `frames/` по `task_id`.

### Миграции

Миграции в `infra/postgres/init/` — нумерованные, идемпотентные, только вперёд. Уже применённый файл не редактируется — заводится следующий по номеру. Схема меняется **только** миграцией, никакого DDL руками.

---

## Аутентификация

| Параметр | Значение |
|----------|----------|
| Библиотека | Auth.js v5 (`next-auth` 5.0 beta) |
| Провайдер | Credentials (email + пароль) |
| Хеширование | argon2id в формате PHC (через `hash-wasm` — WebAssembly, не нативный модуль) |
| Сессия | JWT (stateless) |
| Модель арендатора | Команда = арендатор, роли `owner` / `member` |
| tenant_id в RLS | Из сессии → `set_config('app.tenant_id', $1, true)` |

### Поток входа

1. Пользователь вводит email + пароль
2. `SECURITY DEFINER` функция ищет пользователя по email (до установки tenant-контекста)
3. Приложение проверяет argon2id-хеш (в коде, не в БД — параметры в формате PHC)
4. После проверки — загрузка `team_members`, установка `tenant_id` в сессию
5. Каждый запрос к БД: `set_config('app.tenant_id', $1, true)` → RLS фильтрует по арендатору

### Защищённые маршруты

- Неаутентифицированный запрос → 401
- `member` не может выполнить `owner`-действие → 403
- Сессия проставляет `tenant_id` в RLS-контекст

---

## Деплой

### Продакшен

| Компонент | Конфигурация |
|-----------|-------------|
| **VPS** | TimeWeb, 4 vCPU / 8 GB RAM / 77 GB SSD, Ubuntu 26.04 |
| **IP** | 185.154.194.125 |
| **URL** | https://agora.185-154-194-125.sslip.io |
| **SSL** | Let's Encrypt через Nginx |
| **Frontend** | Next.js 15 standalone build, Node 24, Docker |
| **Backend** | FastAPI/Celery worker, Python 3.14, Docker |
| **PostgreSQL** | Local Docker (Postgres 18) |
| **MongoDB** | TimeWeb managed (8.0) |
| **Redis/Valkey** | TimeWeb managed (9.1) |
| **S3** | TimeWeb managed, 100 GB Standard |
| **LLM** | Qwen 3.6 через timeweb.cloud OpenAI-совместимый API |

Nginx работает как reverse proxy с SSL-терминированием. В проде managed-БД заменяют локальные сервисы Docker Compose: поднимаются только `web` и `worker`, а `*_URL` в env указывают на managed-хосты.

GPU не нужен — все модели вызываются по API. Whisper large-v3 работает на CPU (int8), для длинных роликов — параллельные сегменты, turbo как fallback.

---

## CDD — тестирование

AGORA использует **Contract-Driven Development (CDD)** — тесты пишутся до реализации по контракту из графа задач.

### Порядок работы над задачей

1. **Красный тест** — `evals/tests/test_taskNN_<имя>.py` по полю `cdd` из `tasks.json`. Запускается, обязан упасть и перечислить невыполненные условия.
2. **Реализация** до зелёного.
3. **Проверка**: `npx tsc --noEmit` и `npm run build` для веб-части; `pytest -q` и `ruff check .` для воркера.
4. **PR** по шаблону `.github/pull_request_template.md`.

### Два уровня тестов

- **Статический** — работает где угодно, разбирает исходники и SQL (не требует живой БД)
- **Поведенческий** — требует живую БД и поднятый сервер. При отсутствии среды честно пишет `SKIP`, а не выдумывает результат

### Верификатор

`evals/check.py` — гейт **всего проекта**, а не отдельного PR: требует 31/31 закрытых задач и потому красный до самого конца. В CI на PR проверяются: CDD-тесты задач, `tsc`, `next build`, тесты и линт воркера, `secret_scan`.

### Задача считается закрытой не автором

Статус `done` в `tasks.json` ставится не по статическому уровню, а по прогону в среде пользователя, где есть настоящие Postgres, Mongo, S3 и модель.

---

## Текущий статус

Проект находится на **Фазе 0 (Фундамент)**. Граф из 31 задачи, 3 завершены:

| # | Задача | Статус | Фаза |
|---|--------|--------|------|
| 1 | Инфраструктура и монорепо (Docker) | ✅ Done | Ф0 |
| 2 | Схемы БД + RLS | ✅ Done | Ф0 |
| 3 | Auth и мультиарендность | ✅ Done | Ф0 |
| 4–31 | Persona DNA, генерация, пайплайн, отчёты, фичи | ⏳ Pending | Ф0–Ф4 |

### Вехи

| Фаза | Содержание | Гейт |
|------|-----------|------|
| **Ф0** | Фундамент: инфра, БД+RLS, Auth, Промпт-студия, Настройки, DNA | Верификатор запускается |
| **Ф1** | Срез короткого видео end-to-end | `e2e_short` green |
| **Ф2** | Длинное видео (map-reduce) | `e2e_long` green |
| **Ф3** | Знания (датасет XLS+DOCX, портреты + авто-дистилляция) | — |
| **Ф4** | Фичи после гейта: чат, «Поделиться», перезапуск, файл контекста, экспорт | MVP для пилотов |
| **Ф5** | Post-MVP: вектор/RAG, непрерывная калибровка, AI-модератор | — |

---

## Локальный запуск

### Предварительные требования

- Docker и Docker Compose
- Node.js 24+ (для локальной разработки фронтенда)
- Python 3.14+ (для локальной разработки воркера)
- Аккаунт timeweb.cloud с доступом к API Qwen 3.6
- HF-токен для pyannote (веса закрыты принятием условий)

### Шаг 1. Клонирование

```bash
git clone https://github.com/Asmadey/AGORA.git
cd AGORA
git checkout feature/auth-sidebar  # или нужная ветка
```

### Шаг 2. Переменные окружения

Создайте `.env.local` в корне (файл в `.gitignore`):

```bash
# Обязательные
POSTGRES_PASSWORD=change_me
AGORA_APP_PASSWORD=change_me
AGORA_SHARE_PASSWORD=change_me
MONGO_PASSWORD=change_me
AUTH_SECRET=generate_with_openssl_rand_hex_32
OPENAI_API_KEY=your_timeweb_api_key

# Опциональные (дефолты для локальной разработки)
POSTGRES_USER=agora
POSTGRES_DB=agora
POSTGRES_PORT=5432
MONGO_USER=agora
MONGO_DB=agora
MONGO_PORT=27017
VALKEY_PORT=6379
WEB_PORT=3000
APP_URL=http://localhost:3000
AUTH_URL=http://localhost:3000
OPENAI_BASE_URL=https://api.timeweb.cloud/v1
AI_MODEL=qwen3.6
WHISPER_MODEL=large-v3
WHISPER_COMPUTE_TYPE=int8
```

### Шаг 3. Запуск через Docker Compose

```bash
docker compose -f infra/docker-compose.yml --env-file .env.local up -d
```

Поднимутся: Postgres 18, MongoDB 8.0, Valkey 9.1, web (Next.js), worker (Celery).

Проверка healthchecks:

```bash
docker compose -f infra/docker-compose.yml ps
```

Все сервисы должны быть `healthy`.

### Шаг 4. Применение миграций

Миграции в `infra/postgres/init/` применяются автоматически при первом запуске Postgres (через `docker-entrypoint-initdb.d`). Для повторного применения:

```bash
./infra/postgres/migrate.sh
```

### Шаг 5. Доступ

- **Frontend:** http://localhost:3000
- **Health check:** http://localhost:3000/api/health

### Локальная разработка (без Docker)

Для фронтенда:

```bash
cd apps/web
npm ci
npm run dev          # http://localhost:3000
```

Для воркера:

```bash
cd services/agent-core
pip install -e ".[dev]"
pytest -q
ruff check .
```

### Проверка (CI-гейты)

```bash
# Веб-часть
cd apps/web && npx tsc --noEmit && npm run build

# Воркер
cd services/agent-core && pytest -q && ruff check .

# Верификатор проекта (будет красным до 31/31 задач)
python evals/check.py
```

---

## Документация

| Документ | Описание |
|----------|---------|
| [`docs/AGORA_PRD_FINAL.md`](docs/AGORA_PRD_FINAL.md) | PRD — единый источник правды (20 разделов) |
| [`docs/AGORA_HANDOFF.md`](docs/AGORA_HANDOFF.md) | Передаточный документ для агента-исполнителя |
| [`docs/goal.md`](docs/goal.md) | Цель проекта и описание агентов |
| [`docs/methodology.md`](docs/methodology.md) | Методология (ВЦИОМ, ценности) |
| [`docs/audience.md`](docs/audience.md) | Аудитория и соцдем-параметры |
| [`AGENTS.md`](AGENTS.md) | Протокол работы ИИ-агентов над репозиторием |
| [`evals/state/tasks.json`](evals/state/tasks.json) | Граф из 31 задачи с зависимостями |

---

## Лицензия

Private repository. All rights reserved.

---

**AGORA** · [github.com/Asmadey/AGORA](https://github.com/Asmadey/AGORA) · «Прогноз, а не догадка»