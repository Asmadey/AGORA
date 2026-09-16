import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * Развёртывание по умолчанию берёт ВСЕ службы с кодом, а не две из трёх.
 *
 * ─── Что случилось ────────────────────────────────────────────────────────
 * 16.09.2026 инструменты чата влиты и развёрнуты командой `./infra/deploy.sh`,
 * то есть с умолчанием. Умолчание было `(web worker)`, а чат живёт в
 * `agent-api`: маршрут `/api/chat/reply` обслуживает именно он.
 *
 * Правка не доехала. Контейнер `agora-agent-api-1` на момент «успешного»
 * развёртывания показывал `Up 2 weeks`, и ни одна проверка на это не
 * пожаловалась: скрипт честно собрал и поднял ровно то, что ему назвали.
 *
 * ─── Почему это повторение, а не новость ──────────────────────────────────
 * §3-бис написан ровно про такой случай: «незавершённое развёртывание хуже
 * несделанной работы — несделанную видно, а сделанная и неразвёрнутая выглядит
 * готовой и в отчёте, и в main». Тогда правка не была развёрнута вовсе; теперь
 * она развёрнута НАПОЛОВИНУ, что заметить ещё труднее.
 *
 * ─── Почему список, а не «собери всё подряд» ──────────────────────────────
 * В `docker-compose.yml` есть службы без своего кода в репозитории — база и
 * прочее. Пересобирать их незачем, а `up -d --build` без имён затронул бы и их.
 *
 * Поэтому умолчание перечисляет службы, которые СОБИРАЮТСЯ из этого
 * репозитория. Список сверяется с compose: служба с `build:` обязана быть в
 * умолчании, иначе её правки будут уезжать в main и не доезжать до боевого.
 */

const ROOT = new URL("../../..", import.meta.url).pathname;

function read(rel: string): string {
  const p = join(ROOT, rel);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

const deploy = read("infra/deploy.sh");
const compose = read("infra/docker-compose.yml") || read("docker-compose.yml");

/** Службы compose, у которых есть свой `build:` — то есть свой код в репозитории. */
function buildableServices(): string[] {
  const out: string[] = [];
  let current: string | null = null;
  for (const line of compose.split("\n")) {
    const service = /^ {2}([a-z0-9-]+):\s*$/.exec(line);
    if (service) {
      current = service[1];
      continue;
    }
    if (current && /^ {4}build:/.test(line)) out.push(current);
  }
  return out;
}

function defaultServices(): string[] {
  const m = /SERVICES=\(([^)]*)\)\s*$/m.exec(
    deploy.split("\n").filter((l) => l.includes("SERVICES=(") && !l.includes('"$@"')).join("\n"),
  );
  return m ? m[1].split(/\s+/).filter(Boolean) : [];
}

test("compose разобран и службы со сборкой найдены", () => {
  assert.ok(compose, "docker-compose.yml прочитан");
  const buildable = buildableServices();
  assert.ok(buildable.length >= 2, `служб со сборкой: ${buildable.join(", ") || "нет"}`);
});

test("умолчание развёртывания покрывает все службы со своим кодом", () => {
  const buildable = buildableServices();
  const defaults = defaultServices();
  assert.ok(defaults.length > 0, "умолчание найдено в deploy.sh");

  const missing = buildable.filter((s) => !defaults.includes(s));
  assert.deepEqual(
    missing,
    [],
    `службы собираются из репозитория, но не входят в умолчание: ${missing.join(", ")}. ` +
      `Их правки будут уезжать в main и не доезжать до боевого — молча.`,
  );
});

test("agent-api входит в умолчание поимённо", () => {
  // Отдельной проверкой, а не только через список: чат живёт здесь, и именно
  // эта служба выпала 16.09.2026.
  assert.ok(
    defaultServices().includes("agent-api"),
    `умолчание: ${defaultServices().join(" ")}`,
  );
});
