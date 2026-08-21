-- AGORA · 18 · Корпус в базе: датасеты, записи и слепки
--
-- ─── Что было ───────────────────────────────────────────────────────────────
-- Корпус — 165 сессий реальных респондентов — лежал одним файлом
-- `data/grounding/unified_respondent_sessions.json`. Из него генератор считает
-- доли по возрасту, гео, полу, ценностям и средние по пяти критериям, и по этим
-- долям сэмплирует персон. То есть файл определяет всю выдачу продукта.
--
-- Отсюда две беды, и обе тихие.
--
-- Первая: файл нельзя править из интерфейса. Правка означает коммит в
-- репозиторий и пересборку образа воркера — то есть корпус, который по замыслу
-- принадлежит исследователю, на деле принадлежит разработчику.
--
-- Вторая опаснее. `dataset_sha256()` из `grounding/corpus.py` не вызывается
-- НИГДЕ: контрольная сумма сверяется только eval-тестом #23. Правка корпуса
-- меняет выдачу генератора для того же seed — воспроизводимость ломается молча,
-- и прежние наборы персон перестают воспроизводиться. Заметить это по продукту
-- нельзя: персоны выглядят так же правдоподобно, просто это другие персоны.
--
-- ─── Три таблицы, а не одна ─────────────────────────────────────────────────
-- `corpus_datasets` — корпусов бывает несколько. Сегодня один, но выбор
-- датасета есть на шаге «Аудитория»: исследование про сериалы и исследование
-- про рекламу заземляются на разные выборки, и складывать их в одну таблицу без
-- различения значило бы считать доли по чужим респондентам.
--
-- `corpus_records` — строка на респондента. Не одно поле jsonb на весь корпус:
-- запись правят и удаляют поштучно, а правка одного поля в мегабайтном
-- документе переписывает мегабайт и блокирует его на время записи.
--
-- `corpus_snapshots` — копия записей на момент создания аудитории. Слепок
-- снимается ИМЕННО ТАМ: корпус читается один раз, при сэмплировании персон, и
-- ссылка на слепок живёт на наборе (`persona_sets.corpus_snapshot_id`). Прогон
-- показывает версию корпуса через свой набор персон — то есть через то звено,
-- где корпус действительно применялся.
--
-- Слепок хранится целиком в jsonb, а не ссылками на строки: смысл слепка в том,
-- чтобы пережить правку и удаление записей. Слепок из ссылок разъехался бы с
-- реальностью ровно в тот момент, ради которого заведён.
--
-- ─── Почему sha256 хранится рядом ───────────────────────────────────────────
-- Контрольная сумма — единственный способ увидеть, что содержимое разошлось с
-- тем, по которому считались персоны. Раньше её считала функция, которую никто
-- не звал; теперь она пишется при создании слепка и сверяется при чтении.

BEGIN;

-- ─── Датасеты ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS corpus_datasets (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name        text NOT NULL,
  description text,
  -- Откуда взялся: имя файла засева либо «создан в интерфейсе». Нужно затем,
  -- чтобы через полгода было видно, какой из датасетов пришёл из исследования,
  -- а какой набран руками.
  source      text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

-- ─── Записи ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS corpus_records (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  dataset_id    uuid NOT NULL REFERENCES corpus_datasets(id) ON DELETE CASCADE,
  -- Идентификатор респондента из исходных данных. Уникален внутри датасета:
  -- две записи об одном человеке удвоили бы его вес в долях, и заметить это
  -- можно было бы только по расхождению метрики заземления.
  respondent_id text NOT NULL,
  -- Вся карточка как есть: socio_demographics, agora_core_scores_1_to_10,
  -- perception_and_retention, qualitative_verbatims, all_survey_responses и
  -- прочее. Раскладывать по колонкам нечего: состав секций задаёт исследование,
  -- а не схема, и новый вопрос анкеты — это новый ключ, а не миграция.
  data          jsonb NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (dataset_id, respondent_id)
);

CREATE INDEX IF NOT EXISTS corpus_records_dataset_idx
  ON corpus_records (tenant_id, dataset_id);

-- ─── Слепки ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS corpus_snapshots (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  -- Датасет может быть удалён, а слепок обязан пережить это: набор персон,
  -- собранный по нему, никуда не делся, и вопрос «на чём он заземлён» остаётся
  -- законным. Поэтому SET NULL, а не CASCADE.
  dataset_id    uuid REFERENCES corpus_datasets(id) ON DELETE SET NULL,
  dataset_name  text NOT NULL,
  records       jsonb NOT NULL,
  records_count integer NOT NULL,
  -- sha256 по каноническому представлению записей. Сверяется при чтении:
  -- расхождение означает, что слепок правили в обход приложения.
  sha256        text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS corpus_snapshots_dataset_idx
  ON corpus_snapshots (tenant_id, dataset_id);

-- ─── Связь с набором персон ─────────────────────────────────────────────────
--
-- На наборе, а не на прогоне: корпус читается один раз, при сэмплировании
-- персон. Прогон ссылается на набор и показывает версию корпуса через него.
--
-- NULL — набор создан до этой миграции либо сгенерирован из файла. Это законное
-- состояние и читается как «версия корпуса неизвестна», а не как «версия
-- первая»: подставлять сюда что-то по умолчанию значило бы утверждать
-- воспроизводимость, которой нет.
ALTER TABLE persona_sets
  ADD COLUMN IF NOT EXISTS corpus_snapshot_id uuid
    REFERENCES corpus_snapshots(id) ON DELETE SET NULL;

-- ─── RLS ────────────────────────────────────────────────────────────────────
--
-- FORCE обязателен на всех трёх: без него политики не действуют на владельца
-- таблиц, а владелец — роль миграций и любого админ-скрипта (§5 CLAUDE.md).

ALTER TABLE corpus_datasets  ENABLE ROW LEVEL SECURITY;
ALTER TABLE corpus_datasets  FORCE  ROW LEVEL SECURITY;
ALTER TABLE corpus_records   ENABLE ROW LEVEL SECURITY;
ALTER TABLE corpus_records   FORCE  ROW LEVEL SECURITY;
ALTER TABLE corpus_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE corpus_snapshots FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS corpus_datasets_tenant_isolation ON corpus_datasets;
CREATE POLICY corpus_datasets_tenant_isolation ON corpus_datasets
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS corpus_records_tenant_isolation ON corpus_records;
CREATE POLICY corpus_records_tenant_isolation ON corpus_records
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

DROP POLICY IF EXISTS corpus_snapshots_tenant_isolation ON corpus_snapshots;
CREATE POLICY corpus_snapshots_tenant_isolation ON corpus_snapshots
  FOR ALL TO agora_app
  USING (tenant_id = app.current_tenant())
  WITH CHECK (tenant_id = app.current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON
  corpus_datasets, corpus_records, corpus_snapshots
TO agora_app;

COMMIT;
