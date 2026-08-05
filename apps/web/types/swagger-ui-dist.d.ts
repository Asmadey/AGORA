/**
 * Типы для swagger-ui-dist.
 *
 * Пакет типов не поставляет, а `@types/swagger-ui-dist` описывает старую
 * раскладку файлов и на 5.x не совпадает с ней. Объявление узкое намеренно:
 * здесь описано ровно то, что вызывается в SwaggerDocs.tsx, а не весь API
 * виджета. Широкое `declare module ... : any` погасило бы и настоящие ошибки
 * вызова — например, опечатку в имени опции, которую Swagger UI молча проглотит.
 */
declare module "swagger-ui-dist/swagger-ui-es-bundle.js" {
  interface SwaggerUIConfig {
    url?: string;
    spec?: unknown;
    domNode?: HTMLElement | null;
    docExpansion?: "list" | "full" | "none";
    defaultModelsExpandDepth?: number;
    requestInterceptor?: (request: {
      credentials?: RequestCredentials;
      [key: string]: unknown;
    }) => unknown;
  }

  const SwaggerUIBundle: (config: SwaggerUIConfig) => unknown;
  export default SwaggerUIBundle;
}

declare module "swagger-ui-dist/swagger-ui.css";
