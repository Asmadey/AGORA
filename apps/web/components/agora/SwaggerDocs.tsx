"use client";

import { useEffect, useRef, useState } from "react";

import "swagger-ui-dist/swagger-ui.css";

/**
 * Swagger UI поверх собственной спецификации (OpenAPI 3.1).
 *
 * ─── Почему swagger-ui-dist, а не swagger-ui-react ─────────────────────────
 * Обёртка swagger-ui-react тянет свой React как peer-зависимость и на React 19
 * ещё не заявлена. Здесь же нужен не компонент, а виджет: `swagger-ui-dist`
 * ничего не знает о React, монтируется в узел по id и живёт своей жизнью.
 *
 * ─── Почему bundle загружается динамически ─────────────────────────────────
 * Сборка Swagger UI — около мегабайта. Импорт на уровне модуля утянул бы её в
 * общий клиентский чанк, то есть в каждую страницу приложения ради одной
 * страницы документации. `import()` внутри эффекта оставляет её отдельным
 * чанком, который грузится только здесь.
 *
 * ─── Почему спецификация берётся по URL, а не импортом ─────────────────────
 * Так страница показывает ровно тот документ, который отдаёт `/api-docs/openapi`
 * внешним потребителям. Импорт JSON в компонент дал бы вторую копию, и
 * расхождение между тем, что видит человек, и тем, что забирает генератор
 * клиента, стало бы невидимым.
 */

const SPEC_URL = "/api-docs/openapi";
const MOUNT_ID = "agora-swagger-ui";

export function SwaggerDocs() {
  const mounted = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // React в строгом режиме исполняет эффект дважды; Swagger UI при повторном
    // монтировании в тот же узел рисует вторую копию поверх первой.
    if (mounted.current) return;
    mounted.current = true;

    let cancelled = false;
    (async () => {
      try {
        const mod = await import("swagger-ui-dist/swagger-ui-es-bundle.js");
        if (cancelled) return;
        const SwaggerUIBundle = (mod as { default?: unknown }).default ?? mod;
        (SwaggerUIBundle as (config: Record<string, unknown>) => void)({
          url: SPEC_URL,
          domNode: document.getElementById(MOUNT_ID),
          docExpansion: "list",
          defaultModelsExpandDepth: 1,
          // Запросы «Try it out» идут с кукой сессии того же источника: иначе
          // каждый вызов защищённого маршрута отвечал бы 401, и страница
          // выглядела бы сломанной там, где сломан только режим отправки.
          requestInterceptor: (req: { credentials?: RequestCredentials }) => {
            req.credentials = "same-origin";
            return req;
          },
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : "не удалось загрузить Swagger UI");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="rounded-md border border-rose-400/40 bg-rose-400/5 p-4 text-sm">
        <p className="font-medium">Swagger UI не загрузился</p>
        <p className="mt-1 text-muted-foreground">{error}</p>
        <p className="mt-2 text-muted-foreground">
          Спецификация при этом доступна:{" "}
          <a className="underline underline-offset-4" href={SPEC_URL}>
            {SPEC_URL}
          </a>
        </p>
      </div>
    );
  }

  return <div id={MOUNT_ID} />;
}
