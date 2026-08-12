#!/usr/bin/env bash
#
# Запуск CDD-теста внутри образа воркера.
#
# Зачем. `openai`, `faster_whisper` и `pyannote.audio` живут в образе воркера —
# там они и нужны. Ставить их на хост ради прогона тестов значит завести вторую
# среду: она разойдётся с первой (другие версии torch, другой CUDA, другой
# набор колёс), и расхождение будет невидимым, потому что сверять их нечем.
# Поэтому тест едет к зависимостям, а не зависимости к тесту.
#
# Как. Одноразовый контейнер из того же образа, что и работающий воркер, с
# репозиторием, примонтированным внутрь. Не `docker exec` в работающий воркер:
# в его образе нет каталога `evals/`, и подкладывать туда файлы означало бы
# трогать контейнер, который прямо сейчас разбирает чей-то ролик.
#
# Том с кэшем моделей переиспользуется намеренно: large-v3 весит полтора
# гигабайта, и скачивать его на каждый прогон — это минуты и трафик на пустом
# месте. Тот же том, что у воркера, ещё и проверяет, что кэш заполнен так, как
# ожидает рабочий код.
#
# Примеры:
#   ./evals/run_in_worker.sh evals/tests/test_task15_transcript.py
#   ./evals/run_in_worker.sh evals/tests/test_task18_respondents.py evals/tests/test_task20_analytics.py
#   ./evals/run_in_worker.sh --      python -c 'import openai; print(openai.__version__)'
#
# Всё, что печатает сам скрипт, идёт в stderr: stdout принадлежит тесту, иначе
# разбирать его вывод программно нельзя.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

IMAGE="${WORKER_IMAGE:-agora-worker}"
NETWORK="${WORKER_NETWORK:-agora_default}"
CACHE_VOLUME="${WORKER_CACHE_VOLUME:-agora_model_cache}"
ENV_FILE="${ENV_FILE:-$REPO/.env.local}"

say() { printf '%s\n' "$*" >&2; }

if [ $# -eq 0 ]; then
  say "нечего запускать. Пример: ./evals/run_in_worker.sh evals/tests/test_task18_respondents.py"
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  say "докера нет — образ воркера взять неоткуда"
  exit 3
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  say "образ $IMAGE не собран здесь."
  say "Соберите: docker compose --env-file .env.local -f infra/docker-compose.yml build worker"
  say "Либо укажите другой: WORKER_IMAGE=... $0 ..."
  exit 3
fi

# ─── Что передать внутрь ─────────────────────────────────────────────────────

opts=(--rm -i
      -w /repo
      -e PYTHONPATH=/repo/services/agent-core
      -e PYTHONDONTWRITEBYTECODE=1)

# Сеть контейнеров: внутри неё резолвятся `postgres`, `valkey` и прочие имена
# сервисов compose. Без неё тест, которому нужна база, получит «name resolution
# failure» — то есть отказ, читающийся как поломка базы.
if docker network inspect "$NETWORK" >/dev/null 2>&1; then
  opts+=(--network "$NETWORK")
else
  say "сети $NETWORK нет — тест пойдёт без неё; обращения к базе по имени сервиса не сработают"
fi

if docker volume inspect "$CACHE_VOLUME" >/dev/null 2>&1; then
  opts+=(-v "$CACHE_VOLUME:/home/celeryuser/.cache")
else
  say "тома $CACHE_VOLUME нет — модели будут скачиваться заново"
fi

if [ -f "$ENV_FILE" ]; then
  opts+=(--env-file "$ENV_FILE")
else
  say "нет $ENV_FILE — ключи и строки подключения внутрь не попадут"
fi

# Пользователь остаётся тот же, что у воркера (`celeryuser`), и это не мелочь.
# Подмена uid на хозяйский тянет за собой подмену HOME, а кэш моделей лежит
# именно в $HOME/.cache — том, подключённый выше, перестал бы находиться, и
# large-v3 качался бы заново на каждый прогон. Заодно так проверяется, что
# рабочий код умеет читать кэш из-под своего пользователя, а не из-под root.
#
# Репозиторий смонтирован на чтение: тесты пишут во временные каталоги, а
# байткод отключён выше. Каталог сборки artifacts, если понадобится, монтируется
# отдельно — но ни один из четырёх тестов туда не пишет.
opts+=(-v "$REPO:/repo:ro")

# ─── Что запустить ───────────────────────────────────────────────────────────

if [ "${1:-}" = "--" ]; then
  shift
  say "→ в образе $IMAGE: $*"
  exec docker run "${opts[@]}" "$IMAGE" "$@"
fi

status=0
for test_file in "$@"; do
  say "→ в образе $IMAGE: $test_file"
  docker run "${opts[@]}" "$IMAGE" python "$test_file" || status=$?
done
exit "$status"
