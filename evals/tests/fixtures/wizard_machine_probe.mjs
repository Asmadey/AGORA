/**
 * Прогон машины визарда для CDD-теста задачи #7.
 *
 * Первый пункт cdd — «машина состояний не пускает вперёд без обязательных полей
 * шага» — проверяется только исполнением самой машины: guard `canProceed` живёт
 * в TypeScript и в браузере, из Python его не вызвать. Раньше поэтому кейсы 7–11
 * пропускались строкой `skip for now`, то есть пункт приёмки не проверялся ни
 * разу, а задача при этом стояла done.
 *
 * Запускается из apps/web, чтобы разрешился xstate из node_modules. TypeScript
 * исполняется Node напрямую (стирание типов, Node 22.18+), отдельная сборка не
 * нужна.
 *
 * Результат — JSON в stdout: [{ name, ok, detail }]. Питон разбирает и
 * превращает в обычные проверки.
 */
import { createActor } from "xstate";

import { wizardMachine } from "../../../apps/web/lib/wizard/machine.ts";

const results = [];
const add = (name, ok, detail = "") => results.push({ name, ok, detail });

/** Актор со свежим контекстом: состояния не должны перетекать между проверками. */
function actor(context = {}) {
  const a = createActor(wizardMachine, { input: undefined }).start();
  if (Object.keys(context).length) a.send({ type: "UPDATE", data: context });
  return a;
}

const CONTENT_OK = {
  contentTitle: "Тестовый ролик",
  contentUrl: "s3://bucket/clip.mp4",
  mode: "short",
};
// genders добавлен вместе с задачей #9: пол стал обязательным критерием шага.
// Без него машина застревает на «Аудитории», и кейс 14 («последний шаг никуда
// не ведёт») начинает держаться тавтологией — сравнивает audience с audience и
// проходит, ни разу не дойдя до последнего шага. Проверено: до правки деталь
// показывала «audience → audience», после — «progress → progress».
const AUDIENCE_OK = {
  audienceSize: 20,
  ageGroups: ["25-34"],
  geos: ["столицы"],
  genders: ["жен"],
};

// ── Кейс 7: пустой первый шаг не пускает вперёд ───────────────────────────
{
  const a = actor();
  const before = a.getSnapshot().value;
  a.send({ type: "NEXT" });
  add(
    "машина не пускает вперёд с пустого шага «Контент»",
    a.getSnapshot().value === "content" && before === "content",
    `осталось на ${a.getSnapshot().value}`,
  );
}

// ── Кейс 8: заполненный шаг пускает ────────────────────────────────────────
{
  const a = actor(CONTENT_OK);
  a.send({ type: "NEXT" });
  add(
    "заполненный «Контент» пускает на «Аудиторию»",
    a.getSnapshot().value === "audience",
    `получено ${a.getSnapshot().value}`,
  );
}

// ── Кейс 9: частично заполненный шаг не пускает ───────────────────────────
// Важно проверять именно неполноту, а не пустоту: guard, написанный через
// «хоть что-то заполнено», прошёл бы кейс 7 и провалил бы этот.
{
  const a = actor({ contentTitle: "Только заголовок" });
  a.send({ type: "NEXT" });
  add(
    "частично заполненный «Контент» не пускает вперёд",
    a.getSnapshot().value === "content",
    `осталось на ${a.getSnapshot().value}`,
  );
}

// ── Кейс 10: обязательные поля своего шага, а не предыдущего ──────────────
{
  const a = actor(CONTENT_OK);
  a.send({ type: "NEXT" });
  const atAudience = a.getSnapshot().value === "audience";
  a.send({ type: "NEXT" }); // аудитория пуста: ageGroups/geos не заданы
  add(
    "пустая «Аудитория» не пускает на «Опрос»",
    atAudience && a.getSnapshot().value === "audience",
    `получено ${a.getSnapshot().value}`,
  );
}

// ── Кейс 11: BACK возвращает и не требует полей ───────────────────────────
{
  const a = actor({ ...CONTENT_OK, ...AUDIENCE_OK });
  a.send({ type: "NEXT" });
  a.send({ type: "BACK" });
  add(
    "BACK возвращает на предыдущий шаг",
    a.getSnapshot().value === "content",
    `получено ${a.getSnapshot().value}`,
  );
}

// ── Кейс 14: последний шаг никуда не ведёт ────────────────────────────────
// canProceed возвращает false для последнего индекса; без этой проверки
// «прогресс» мог бы иметь переход в никуда и машина падала бы на исполнении.
{
  const a = actor({ ...CONTENT_OK, ...AUDIENCE_OK });
  for (let i = 0; i < 10; i += 1) a.send({ type: "NEXT" });
  const final = a.getSnapshot().value;
  a.send({ type: "NEXT" });
  add(
    "последний шаг не ведёт дальше",
    final === a.getSnapshot().value,
    `${final} → ${a.getSnapshot().value}`,
  );
}

process.stdout.write(JSON.stringify(results));
