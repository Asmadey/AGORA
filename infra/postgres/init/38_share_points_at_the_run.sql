-- ─────────────────────────────────────────────────────────────────────────
-- 38. Публичная ссылка указывает на ПРОГОН, а не на строку отчёта
-- ─────────────────────────────────────────────────────────────────────────
--
-- Что чинится. `report_shares.report_id` — NOT NULL со ссылкой на `reports`.
-- Таблица `reports` в Postgres при этом ПУСТА, и пуста не по недосмотру:
-- отчёт живёт в MongoDB (задача #21, agent_core/analytics/store.py). Замер на
-- боевой базе — 0 строк за всё время работы продукта.
--
-- То есть выпустить ссылку было нельзя в принципе: INSERT падал бы на внешнем
-- ключе. Ровно поэтому диалог «Поделиться» так и остался витриной, которая
-- выдумывала токен в браузере и показывала адрес несуществующего домена, —
-- подключить его к этой схеме было не к чему.
--
-- Что делаем. Ссылка теперь указывает на прогон: `task_id`. Это и есть то, чем
-- делятся — исследование, а не строка в таблице, которой не существует.
--
-- `report_id` остаётся, но становится необязательным: удалять колонку, на
-- которую ссылается политика reports_public_share_read, значит чинить одно и
-- ломать другое. Политика остаётся жить на пустой таблице и никому не мешает.
--
-- Идемпотентно: IF NOT EXISTS и DROP NOT NULL повторный прогон переживают.

BEGIN;

ALTER TABLE report_shares ADD COLUMN IF NOT EXISTS task_id uuid REFERENCES tasks(id) ON DELETE CASCADE;

ALTER TABLE report_shares ALTER COLUMN report_id DROP NOT NULL;

-- Ссылка без прогона бессмысленна: открывать нечего. Но проверку ставим
-- отдельно от колонки, чтобы старые строки (их нет, но правило важнее) не
-- мешали миграции.
ALTER TABLE report_shares DROP CONSTRAINT IF EXISTS report_shares_points_somewhere;
ALTER TABLE report_shares
  ADD CONSTRAINT report_shares_points_somewhere
  CHECK (task_id IS NOT NULL OR report_id IS NOT NULL);

CREATE INDEX IF NOT EXISTS report_shares_task_idx ON report_shares (task_id) WHERE task_id IS NOT NULL;

COMMIT;
