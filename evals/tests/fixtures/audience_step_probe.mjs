/**
 * Прогон машины визарда по шагу «Аудитория» для CDD-теста задачи #9.
 *
 * Второй пункт cdd — «выбор существующего persona_set пропускает генерацию» —
 * это в первую очередь свойство машины: при выбранном наборе шаг обязан пускать
 * вперёд без критериев генерации, потому что генерации не будет. Требовать их
 * значило бы заставлять заполнять то, что не будет использовано.
 *
 * Запускается из корня монорепо, чтобы разрешился xstate. TypeScript исполняется
 * Node напрямую (стирание типов, Node 22.18+) — тот же приём, что в пробе #7.
 */
import { createActor } from "xstate";

import { wizardMachine } from "../../../apps/web/lib/wizard/machine.ts";

const results = [];
const add = (name, ok, detail = "") => results.push({ name, ok, detail });

const CONTENT_OK = {
  contentTitle: "Тестовый ролик",
  contentUrl: "s3://bucket/clip.mp4",
  mode: "short",
};

/** Доводит машину до шага «Аудитория» и пробует шагнуть дальше с данным контекстом. */
function afterAudience(audience) {
  const a = createActor(wizardMachine).start();
  a.send({ type: "UPDATE", data: CONTENT_OK });
  a.send({ type: "NEXT" });
  const reached = a.getSnapshot().value;
  a.send({ type: "UPDATE", data: audience });
  a.send({ type: "NEXT" });
  return { reached, after: a.getSnapshot().value };
}

const EMPTY = {
  audienceSize: 20,
  ageGroups: [],
  geos: [],
  genders: [],
  personaSetId: null,
};

// ── Без критериев и без набора — вперёд нельзя ────────────────────────────
{
  const { reached, after } = afterAudience(EMPTY);
  add(
    "шаг «Аудитория» не пускает вперёд без критериев",
    reached === "audience" && after === "audience",
    `дошли до ${reached}, после NEXT ${after}`,
  );
}

// ── Критерии заданы — вперёд можно ────────────────────────────────────────
{
  const { after } = afterAudience({
    ...EMPTY,
    ageGroups: ["25-34"],
    geos: ["столицы"],
    genders: ["жен"],
  });
  add(
    "заданные критерии пускают вперёд",
    after === "survey",
    `получено ${after}`,
  );
}

// ── Выбран существующий набор — критерии не нужны ─────────────────────────
{
  const { after } = afterAudience({ ...EMPTY, personaSetId: "set-1" });
  add(
    "выбор существующего набора пускает вперёд без критериев",
    after === "survey",
    `получено ${after}`,
  );
}

// ── Пол — обязательный критерий, а не украшение ───────────────────────────
// До задачи #9 guard требовал только размер, возраст и гео. Пол в контракте
// объявлен, в корпусе распределён 110/55 и влияет на калибровку — значит он
// либо обязателен, либо его нет. Молчаливое «поле есть, но ни на что не
// влияет» — худший из трёх вариантов.
{
  const { after } = afterAudience({
    ...EMPTY,
    ageGroups: ["25-34"],
    geos: ["столицы"],
  });
  add(
    "без пола шаг не пускает вперёд",
    after === "audience",
    `получено ${after}`,
  );
}

process.stdout.write(JSON.stringify(results));
