/**
 * Разбор произвольного JSON в дерево для показа.
 *
 * ─── Почему своя реализация ────────────────────────────────────────────────
 * jsoncrack и родственные ему просмотрщики лежат под AGPL-3.0: копирование кода
 * обязало бы открыть весь проект под той же лицензией. Здесь написано с нуля и
 * умышленно скромно — разбор структуры и подписи, без графа связей.
 *
 * ─── Почему разбор отдельно от компонента ──────────────────────────────────
 * Компонент нельзя проверить без браузера, а разбор — можно. Ошибка здесь
 * тихая: узел, потерянный при обходе, выглядит как «в отчёте этого нет», и
 * читатель делает вывод об исследовании вместо вывода о просмотрщике.
 */

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface JsonNode {
  /** Путь от корня: `aggregate.nps`, `narrative.0`. Он же ключ React. */
  path: string;
  /** Подпись узла — имя поля либо индекс. */
  label: string;
  /** Тип для подсветки и для решения, сворачивать ли. */
  kind: "object" | "array" | "string" | "number" | "boolean" | "null";
  /** Готовая строка для листа. У ветки — сводка вида «12 полей». */
  preview: string;
  children: JsonNode[];
}

function kindOf(value: JsonValue): JsonNode["kind"] {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  switch (typeof value) {
    case "object": return "object";
    case "number": return "number";
    case "boolean": return "boolean";
    default: return "string";
  }
}

/** Русское склонение для сводки ветки: 1 поле, 2 поля, 5 полей. */
function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} ${one}`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} ${few}`;
  return `${n} ${many}`;
}

function previewOf(value: JsonValue, kind: JsonNode["kind"]): string {
  switch (kind) {
    case "object":
      return plural(Object.keys(value as object).length, "поле", "поля", "полей");
    case "array":
      return plural((value as JsonValue[]).length, "элемент", "элемента", "элементов");
    case "null":
      // Именно «null», а не пустая строка: отсутствие значения и пустая строка —
      // разные факты, и в отчёте они означают разное.
      return "null";
    case "string":
      return String(value);
    default:
      return String(value);
  }
}

/**
 * Строит дерево. `depth` ограничивает глубину обхода.
 *
 * Ограничение нужно не от бесконечности — JSON конечен, — а от размера: отчёт
 * с пятьюстами ответами разворачивается в десятки тысяч узлов, и браузер
 * встаёт на попытке отрисовать их разом. Достигнув предела, узел остаётся
 * веткой без детей и честно показывает свою сводку.
 */
export function buildTree(
  value: JsonValue,
  label = "отчёт",
  path = "",
  depth = 6,
): JsonNode {
  const kind = kindOf(value);
  const node: JsonNode = {
    path: path || label,
    label,
    kind,
    preview: previewOf(value, kind),
    children: [],
  };

  if (depth <= 0) return node;

  if (kind === "object") {
    for (const [key, child] of Object.entries(value as Record<string, JsonValue>)) {
      node.children.push(buildTree(child, key, `${node.path}.${key}`, depth - 1));
    }
  } else if (kind === "array") {
    (value as JsonValue[]).forEach((child, i) => {
      node.children.push(buildTree(child, String(i), `${node.path}.${i}`, depth - 1));
    });
  }

  return node;
}
