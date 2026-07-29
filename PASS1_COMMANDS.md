# Pass 1 — команды для подтверждения задачи #1

Задача #1 реализована, её CDD-тест зелёный. Но **вердикт выносит верификатор, а не я**,
а две метрики (`build_frontend`, `compose_health`) требуют docker и npm — их нет в моей
среде. Выполните это у себя, пришлите вывод последней команды.

Все команды — из корня `AGORA/`.

---

## 0. Заполнить `.env.local`
Ваш рабочий ключ уже там (переехал из `env.env`), но формат сменился на контракт из
`apps/web/.env.example`. Проверьте, что заданы как минимум:

```
OPENAI_API_KEY=...            # ваш рабочий ключ timeweb
OPENAI_BASE_URL=https://api.timeweb.cloud/v1
AI_MODEL=qwen3.6
VLM_MODEL=qwen3.6

POSTGRES_PASSWORD=...         # придумайте
MONGO_PASSWORD=...            # придумайте
AUTH_SECRET=...               # openssl rand -base64 32
```

Compose намеренно падает с внятной ошибкой, если `POSTGRES_PASSWORD`, `MONGO_PASSWORD`,
`AUTH_SECRET` или `OPENAI_API_KEY` не заданы — тихих дефолтов для секретов нет.

## 1. Фронтенд
```bash
npm ci                 # поднимет workspaces: apps/web
npm run build          # → workspace @agora/web
```
Ожидание: `build_frontend` перейдёт из skip в pass.
Если `npm ci` ругается на рассинхрон lock-файла — `npm install` один раз, затем закоммитить
обновлённый `package-lock.json`.

## 2. Worker (можно проверить и без docker)
```bash
cd services/agent-core
pip install -e ".[dev]"
python -m pytest -q && ruff check .
cd ../..
```
Ожидание: 7 тестов зелёные, ruff чистый. У меня уже так — это на случай расхождения версий.

## 3. Стек
```bash
docker compose -f infra/docker-compose.yml --env-file .env.local config --quiet   # валидация
docker compose -f infra/docker-compose.yml --env-file .env.local up -d
docker compose -f infra/docker-compose.yml ps
```
Ожидание: пять сервисов, все `healthy`. `worker` стартует дольше остальных
(start_period 60s) — дайте ему минуту.

Если `web` не поднимается — почти наверняка сборка образа, смотрите:
```bash
docker compose -f infra/docker-compose.yml logs web --tail 50
```

## 4. Вердикт
```bash
python3 evals/tests/test_task01_monorepo.py    # CDD-тест задачи #1
python3 evals/check.py                          # верификатор проекта
```

**Пришлите вывод `evals/check.py`.** Задачу #1 помечу как `done` только если в нём
`build_frontend` = pass и `compose_health` = pass. После этого разблокируется ровно одна
задача — **#2 (Схемы БД + RLS)**, с неё пойдёт Pass 2.

---

## Отдельно, не в петле: перевыпустить ключи

`secret_scan`, расширившись на весь репозиторий, нашёл в `backup/` два **настоящих**
ключа — Google (`AIza…`) и `sk-…` — в трёх копиях старых репозиториев, у одной из них
с `.git`-историей. Каталог я удалил (он есть в архиве `AGORA-pre-monorepo-*.tar.gz`),
но **удаление файлов не отменяет утечку**, если эти репозитории когда-либо публиковались.

Ключи нужно перевыпустить в консолях провайдеров — это делаете вы, я credential-операции
не выполняю. Пока не перевыпущены, считайте их скомпрометированными.

## Что изменилось в раскладке

```
AGORA/                        ← корень монорепо, здесь git init
├── apps/web/                 ← был agora-unified/ (Next.js, теперь @agora/web)
├── services/agent-core/      ← новый: FastAPI + Celery + LangGraph
├── packages/shared/schemas/  ← canonical JSON Schema, контракт TS↔Python
├── infra/                    ← docker-compose, Dockerfiles, postgres/init
├── evals/                    ← верификатор, граф задач, фикстуры, CDD-тесты
├── data/grounding/           ← корпус, 165 записей
├── prompts/                  ← 13 seed-промптов
├── docs/
├── .env.local                ← секреты, закрыт .gitignore
└── package.json              ← npm workspaces
```

Удалено: `backup/` (утёкшие ключи), `.next/`, дубли документов. Всё есть в архиве.
