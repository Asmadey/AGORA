import assert from "node:assert/strict";
import { test } from "node:test";

import { publicOrigin } from "./public-origin.ts";

/**
 * Откуда берётся адрес продукта для ссылок, уходящих наружу.
 *
 * ─── Что было ───────────────────────────────────────────────────────────────
 * Публичная ссылка на отчёт строилась от `new URL(request.url).origin`, и на
 * боевом сервере получалось `https://0.0.0.0:3000/s/…`. Отправить такую ссылку
 * нельзя никому.
 *
 * Причина: Next.js слушает 0.0.0.0:3000 внутри контейнера, а наружу смотрит
 * nginx. `request.url` — это адрес, по которому пришёл ВНУТРЕННИЙ запрос, а не
 * тот, который человек видит в браузере.
 *
 * ─── Что известно серверу о настоящем адресе ────────────────────────────────
 * Три источника, по убыванию надёжности:
 *
 * 1. `AUTH_URL` — канонический адрес продукта. Он уже обязан быть верным: на
 *    нём держится вход через Auth.js, и ошибка в нём ломает логин, то есть
 *    замечается сразу.
 * 2. Заголовки от обратного прокси: `x-forwarded-proto` и `host`. nginx их
 *    ставит; они отражают то, по чему пришёл именно этот запрос.
 * 3. `request.url` — последний рубеж. Годится в разработке, где прокси нет.
 */

test("канонический адрес из AUTH_URL сильнее всего", () => {
  assert.equal(
    publicOrigin({
      authUrl: "https://agora.185-154-194-125.sslip.io",
      forwardedProto: "https",
      host: "agora.185-154-194-125.sslip.io",
      requestUrl: "http://0.0.0.0:3000/api/tasks/x/share",
    }),
    "https://agora.185-154-194-125.sslip.io",
  );
});

test("хвостовые слэши и путь из AUTH_URL отбрасываются", () => {
  assert.equal(
    publicOrigin({ authUrl: "https://agora.example/api/auth/", requestUrl: "http://0.0.0.0:3000/x" }),
    "https://agora.example",
  );
});

test("без AUTH_URL берутся заголовки прокси", () => {
  assert.equal(
    publicOrigin({
      forwardedProto: "https",
      host: "agora.185-154-194-125.sslip.io",
      requestUrl: "http://0.0.0.0:3000/api/tasks/x/share",
    }),
    "https://agora.185-154-194-125.sslip.io",
  );
});

test("протокол по умолчанию https, если прокси его не назвал", () => {
  // Прокси, стоящий перед TLS, — норма; голый http наружу — исключение.
  assert.equal(
    publicOrigin({ host: "agora.example", requestUrl: "http://0.0.0.0:3000/x" }),
    "https://agora.example",
  );
});

test("локальная разработка не ломается", () => {
  assert.equal(
    publicOrigin({ host: "localhost:3000", forwardedProto: "http", requestUrl: "http://localhost:3000/x" }),
    "http://localhost:3000",
  );
});

test("без всего остаётся адрес запроса", () => {
  assert.equal(publicOrigin({ requestUrl: "http://localhost:3000/api/x" }), "http://localhost:3000");
});

test("адрес, по которому нельзя ходить снаружи, не выдаётся за публичный", () => {
  // 0.0.0.0 — это «слушаю на всех интерфейсах», а не адрес. Ссылка с ним
  // бесполезна ровно так же, как её отсутствие, и молчать об этом нельзя.
  assert.equal(
    publicOrigin({ host: "0.0.0.0:3000", requestUrl: "http://0.0.0.0:3000/x" }),
    null,
  );
  assert.equal(publicOrigin({ requestUrl: "http://[::]:3000/x" }), null);
});

test("первый пригодный источник побеждает негодный", () => {
  // AUTH_URL не задан, host — служебный, но прокси назвал настоящий хост.
  assert.equal(
    publicOrigin({
      forwardedHost: "agora.example",
      host: "0.0.0.0:3000",
      forwardedProto: "https",
      requestUrl: "http://0.0.0.0:3000/x",
    }),
    "https://agora.example",
  );
});
