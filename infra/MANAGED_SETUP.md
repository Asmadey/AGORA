# Подключение к managed-инфраструктуре TimeWeb

Всё ниже выполняется на вашей машине: до хостов TimeWeb есть доступ только у вас.

## 0. Сгенерировать недостающие секреты

В `.env.local` четыре значения помечены `CHANGE_ME`. Их не может подставить
никто снаружи — это новые пароли, а не выданные провайдером.

```bash
cd ~/AntiGravity/AGORA

python3 - <<'PY'
import secrets, base64, urllib.parse, pathlib, re
app   = base64.b64encode(secrets.token_bytes(18)).decode()
share = base64.b64encode(secrets.token_bytes(18)).decode()
auth  = base64.b64encode(secrets.token_bytes(24)).decode()

p = pathlib.Path(".env.local"); t = p.read_text()
t = t.replace('AGORA_APP_PASSWORD="CHANGE_ME_openssl_rand_base64_24"',   f'AGORA_APP_PASSWORD="{app}"')
t = t.replace('AGORA_SHARE_PASSWORD="CHANGE_ME_openssl_rand_base64_24"', f'AGORA_SHARE_PASSWORD="{share}"')
t = t.replace('AUTH_SECRET="CHANGE_ME_openssl_rand_base64_32"',          f'AUTH_SECRET="{auth}"')

# Пароль в DATABASE_URL обязан быть percent-encoded: base64 даёт + / =,
# и «/» в URI — разделитель пути. Незакодированный пароль обрежет строку.
t = re.sub(r'postgresql://agora_login:CHANGE_ME@',
           f'postgresql://agora_login:{urllib.parse.quote(app, safe="")}@', t)
p.write_text(t)
print("готово")
PY
```

## 1. Сертификат PostgreSQL

`sslmode=verify-full` проверяет, что вы говорите именно с сервером TimeWeb, а не
с тем, кто перехватил соединение. В строке подключения едет пароль, поэтому
понижать до `require` (шифрование без проверки подлинности) не нужно.

```bash
mkdir -p ~/.cloud-certs && \
curl -o ~/.cloud-certs/root.crt "https://st.timeweb.com/cloud-static/ca.crt" && \
chmod 0600 ~/.cloud-certs/root.crt
```

В `.env.local` уже стоит `PGSSLROOTCERT="/root/.cloud-certs/root.crt"` — это путь
**внутри контейнера**. Для запуска с хоста подставьте свой:

```bash
export PGSSLROOTCERT=$HOME/.cloud-certs/root.crt
```

## 2. Проверить доступность

```bash
pip install 'psycopg[binary]' pymongo redis boto3 --break-system-packages
set -a; source .env.local; set +a
export PGSSLROOTCERT=$HOME/.cloud-certs/root.crt
python3 infra/preflight.py
```

Скрипт проверяет четыре сервиса по отдельности и различает «сеть закрыта» и
«учётные данные не подошли». Если Postgres или Mongo недоступны по TCP —
скорее всего, в панели TimeWeb включён белый список IP и вашего адреса там нет.

## 3. Применить схему

```bash
set -a; source .env.local; set +a
export PGSSLROOTCERT=$HOME/.cloud-certs/root.crt
bash infra/postgres/migrate.sh
```

Скрипты из `infra/postgres/init/` рассчитаны на `docker-entrypoint-initdb.d`,
который выполняется один раз при инициализации пустого каталога данных. На
managed-инстансе каталог инициализировал провайдер, и эти файлы не выполнятся
никогда — при этом compose поднимется, приложение стартует, а таблиц не будет.
`migrate.sh` закрывает именно этот разрыв.

**Что может не сработать.** `gen_user` на managed-инстансе не суперпользователь.
Политики в `03_rls.sql` выданы конкретным ролям (`TO agora_app`), поэтому без
права `CREATEROLE` схему применить нельзя. Скрипт проверяет это до первого DDL и
говорит прямо, а не падает на середине с полуприменённой схемой. Если права нет
— запрос провайдеру: либо выдать `CREATEROLE`, либо создать четыре роли
(`agora_app`, `agora_share`, `agora_login`, `agora_share_login`) на их стороне.

То, что `gen_user` **не** суперпользователь — это хорошо: RLS суперпользователя
не ограничивает вообще, и проверить изоляцию под ним было бы невозможно.

## 4. Подтвердить изоляцию арендаторов

```bash
python3 evals/check.py
```

Метрика `rls_tenant` должна перейти из `skip` в `pass` (порог: строк, видимых
между арендаторами, ноль). Это закрывает задачу #2 и разблокирует #3 и #4.

## 5. Поднять приложение на managed-БД

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.managed.yml \
  --env-file .env.local up -d web worker
```

Имена сервисов в конце обязательны. Без них `up -d` поднял бы ещё и контейнерные
`postgres`/`mongo`/`valkey`, и контейнерный Postgres перехватил бы имя хоста
`postgres` — приложение работало бы с пустой локальной базой, считая, что
подключено к managed. Оверрайд обнуляет `depends_on`, но не может удалить сами
сервисы. Требуется Docker Compose ≥ 2.24.4 (тег `!reset`).

## Что осталось решить

**Ключ модели не тот.** В `.env.local` лежит ключ Alibaba DashScope
(`ap-southeast-1.maas.aliyuncs.com`), а Decision Log #1 описывает Qwen 3.6 через
`api.timeweb.cloud/v1`. Я оставил рабочий ключ и поправил `OPENAI_BASE_URL` под
него, чтобы запуск не падал, но расхождение с решением нужно снять осознанно: от
провайдера зависят и лимиты, и юрисдикция, в которой окажутся кадры видео.

**Redis вместо Valkey.** Протокол совместим, `VALKEY_URL` работает как есть.
Стоит проверить `maxmemory-policy` — preflight его печатает. Для очереди Celery
нужен `noeviction`: при любой политике вытеснения брокер под нагрузкой начнёт
терять задачи, и прогон исчезнет без сообщения об ошибке.

**Ротация.** Пароли из этой переписки и два старых ключа (`AIza…`, `sk-…` из
удалённого `backup/`) стоит перевыпустить после того, как связка заработает.
