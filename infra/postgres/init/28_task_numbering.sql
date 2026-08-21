-- AGORA · 28 · Человеческий номер исследования
--
-- ─── Зачем ──────────────────────────────────────────────────────────────────
-- UUID остаётся первичным ключом и остаётся в адресе: он уникален глобально и
-- не требует согласования. Но в разговоре им не пользуются — «посмотри
-- e81feb92-97a2-43ad-8112-de7503699c60» не произносится вслух и не набирается
-- по памяти. Номер нужен человеку, а не системе, и потому живёт рядом с UUID, а
-- не вместо него.
--
-- ─── Почему счётчик на арендатора, а не общая последовательность ────────────
-- Последовательность в Postgres одна на базу. У двух команд номера пошли бы
-- вперемежку: 0001, 0004, 0007 — и «третье исследование» перестало бы означать
-- третье. Номер, по которому нельзя сослаться, не нужен.
--
-- ─── Почему без пропусков, а не sequence ────────────────────────────────────
-- Sequence не откатывается вместе с транзакцией: отменённое создание съедает
-- номер навсегда. Пропуск в нумерации выглядит потерянным исследованием, и
-- объяснять его пришлось бы каждому новому человеку в команде.
--
-- Цена — блокировка одной строки счётчика на время вставки. Создание
-- исследования делает человек руками, десятки раз в день на команду; очередь на
-- этой строке не соберётся. Блокировка на КАЖДОЙ вставке была бы неприемлема
-- для потока событий, но здесь поток другой.

BEGIN;

CREATE TABLE IF NOT EXISTS tenant_counters (
  tenant_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  -- Вид нумерации: сегодня исследования, завтра наборы персон. Отдельная
  -- таблица на каждый вид означала бы миграцию под каждый новый счётчик.
  kind      text NOT NULL,
  value     integer NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, kind)
);

ALTER TABLE tenant_counters ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_counters FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_counters_isolation ON tenant_counters;
CREATE POLICY tenant_counters_isolation ON tenant_counters
  FOR ALL TO agora_app
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

GRANT SELECT, INSERT, UPDATE ON tenant_counters TO agora_app;

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS seq_no integer;

-- Уникальность в пределах арендатора. Без неё гонка двух вставок дала бы два
-- исследования с одним номером, и заметили бы это в переписке, а не в логах.
CREATE UNIQUE INDEX IF NOT EXISTS tasks_tenant_seq_idx
  ON tasks (tenant_id, seq_no) WHERE seq_no IS NOT NULL;

-- Уже созданным исследованиям номера раздаются по времени создания: иначе
-- прежние прогоны остались бы без номера навсегда, и список показывал бы дыру
-- в начале.
WITH numbered AS (
  SELECT id, ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY created_at, id) AS n
  FROM tasks
  WHERE seq_no IS NULL
)
UPDATE tasks t SET seq_no = numbered.n
FROM numbered WHERE t.id = numbered.id;

-- Счётчик подводится под уже розданные номера, иначе следующая вставка выдала
-- бы единицу поверх существующего исследования.
INSERT INTO tenant_counters (tenant_id, kind, value)
SELECT tenant_id, 'task', MAX(seq_no) FROM tasks WHERE seq_no IS NOT NULL
GROUP BY tenant_id
ON CONFLICT (tenant_id, kind) DO UPDATE SET value = GREATEST(tenant_counters.value, EXCLUDED.value);

COMMIT;
