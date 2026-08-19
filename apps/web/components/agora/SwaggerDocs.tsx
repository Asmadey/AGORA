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

/**
 * Каркас на время загрузки бандла.
 *
 * ─── Зачем ────────────────────────────────────────────────────────────────
 * Страница — серверный компонент, отрисовывается мгновенно. Ждать приходится
 * клиентскую загрузку сборки Swagger (около мегабайта) и запрос спецификации;
 * всё это время в DOM пустой div, и белый экран читается как зависание.
 *
 * `loading.tsx` тут не помог бы: медленная не серверная часть, а клиентская,
 * и к моменту его показа страница уже отрисована.
 *
 * Форма повторяет Swagger: шапка, строка поиска, полосы эндпоинтов. Каркас,
 * не похожий на то, что появится, вызывает второй скачок содержимого — тот
 * самый, от которого он должен избавлять.
 */
function SwaggerSkeleton() {
  return (
    <div className="animate-pulse space-y-6" aria-hidden="true">
      <div className="space-y-2">
        <div className="h-8 w-72 rounded bg-black/10" />
        <div className="h-4 w-96 rounded bg-black/5" />
      </div>
      <div className="h-10 w-full rounded bg-black/5" />
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 rounded border border-black/10 p-3">
            <div className="h-6 w-16 shrink-0 rounded bg-black/10" />
            <div className="h-4 flex-1 rounded bg-black/5" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SwaggerDocs() {
  const mounted = useRef(false);
  const [error, setError] = useState<string | null>(null);
  /**
   * Виджет смонтирован. Не «бандл загружен»: между загрузкой и появлением
   * содержимого Swagger успевает сходить за спецификацией, и снятый раньше
   * каркас оставил бы тот же белый экран, только короче.
   */
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // React в строгом режиме исполняет эффект дважды; Swagger UI при повторном
    // монтировании в тот же узел рисует вторую копию поверх первой.
    if (mounted.current) return;
    mounted.current = true;

    let cancelled = false;
    let fallback: ReturnType<typeof setTimeout> | undefined;
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
          onComplete: () => setReady(true),
        });
        // Запасной путь: `onComplete` зовётся не во всех сборках Swagger, и
        // каркас, оставшийся навсегда, хуже снятого на мгновение раньше.
        // Таймер запоминается, чтобы уход со страницы не оставил вызов
        // setState на размонтированном компоненте.
        fallback = setTimeout(() => setReady(true), 1500);
      } catch (e) {
        setError(e instanceof Error ? e.message : "не удалось загрузить Swagger UI");
      }
    })();

    return () => {
      cancelled = true;
      if (fallback) clearTimeout(fallback);
    };
  }, []);

  if (error) {
    return (
      <div className="rounded-md border border-rose-400/40 bg-rose-400/5 p-4 text-sm">
        <p className="font-medium">Swagger UI не загрузился</p>
        <p className="mt-1 text-slate">{error}</p>
        <p className="mt-2 text-slate">
          Спецификация при этом доступна:{" "}
          <a className="underline underline-offset-4" href={SPEC_URL}>
            {SPEC_URL}
          </a>
        </p>
      </div>
    );
  }

  return (
    <>
      {!ready && <SwaggerSkeleton />}
      <div id={MOUNT_ID} />
    </>
  );
}
