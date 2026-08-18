"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { buildTree, type JsonNode, type JsonValue } from "@/lib/json-tree";
import { cn } from "@/lib/utils";

/**
 * Просмотрщик JSON деревом.
 *
 * Написан с нуля: jsoncrack и родственные ему лежат под AGPL-3.0, и копирование
 * кода обязало бы открыть весь проект под той же лицензией.
 *
 * Разбор структуры живёт в `lib/json-tree.ts` и покрыт тестами — компонент
 * нельзя проверить без браузера, а разбор можно. Потерянный при обходе узел
 * выглядит как «в отчёте этого нет», и читатель делает вывод об исследовании
 * вместо вывода о просмотрщике.
 */

const KIND_CLASS: Record<JsonNode["kind"], string> = {
  string: "text-foreground",
  number: "text-brand-blue tabular-nums",
  boolean: "text-brand-blue",
  // Отсутствие значения приглушено намеренно: его читают как «здесь ничего
  // нет», и выделять его наравне с данными значит спорить с этим чтением.
  null: "text-slate italic",
  object: "text-slate",
  array: "text-slate",
};

function Node({ node, level }: { node: JsonNode; level: number }) {
  // Первые два уровня открыты: там лежит то, ради чего отчёт открывают. Глубже
  // начинаются ответы персон, и раскрытый по умолчанию список из пятисот
  // элементов делает страницу нечитаемой.
  const [open, setOpen] = useState(level < 2);
  const branch = node.children.length > 0;

  return (
    <li>
      <div className="flex items-baseline gap-1.5 py-0.5">
        {branch ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="-ml-1 flex items-center text-slate transition-colors hover:text-foreground"
            aria-expanded={open}
            aria-label={open ? `Свернуть ${node.label}` : `Развернуть ${node.label}`}
          >
            <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")} />
          </button>
        ) : (
          <span className="w-2.5" />
        )}
        <span className="font-mono text-xs text-slate">{node.label}</span>
        <span className={cn("min-w-0 break-words font-mono text-xs", KIND_CLASS[node.kind])}>
          {node.preview}
        </span>
      </div>
      {branch && open && (
        <ul className="ml-3 border-l border-hairline pl-3">
          {node.children.map((child) => (
            <Node key={child.path} node={child} level={level + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function JsonTree({ value, label }: { value: JsonValue; label?: string }) {
  const tree = buildTree(value, label ?? "отчёт");
  return (
    <ul className="overflow-x-auto">
      <Node node={tree} level={0} />
    </ul>
  );
}
