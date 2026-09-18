import { Fragment } from "react";

import { parseMarkdown, type MdBlock, type MdInline } from "@/lib/markdown";

/**
 * Разметка ответа модели на экране.
 *
 * ─── Что здесь НЕ делается ────────────────────────────────────────────────
 * Не разбирается markdown. Разбор живёт в `lib/markdown.ts`, потому что
 * `npm test` собирает только `lib/**`: логика, оставленная в `.tsx`, тестами
 * не покрыта вовсе. Здесь остаётся ровно перевод блоков в узлы — то, что
 * сломать можно только глазами и только заметно.
 *
 * ─── Почему узлы, а не строка ─────────────────────────────────────────────
 * `dangerouslySetInnerHTML` тут нет и быть не может: текст приходит от модели,
 * и `<img src=x onerror=…>` в её ответе стал бы исполняемым. React ставит
 * текст текстом и по-другому не умеет, поэтому экранировать нечего — не
 * потому, что мы аккуратны, а потому, что строки HTML не возникает нигде.
 *
 * ─── Почему `whitespace-pre-line` на абзаце ───────────────────────────────
 * Перенос строки ВНУТРИ абзаца модель ставит осмысленно, и он должен дожить
 * до экрана. `pre-wrap` для этого не годится: он сохранил бы и ведущие
 * пробелы, которыми модель выравнивает вложенные пункты, — отступы поехали бы
 * поверх отступов списка. `pre-line` оставляет переносы и схлопывает пробелы.
 */

function Spans({ spans }: { spans: MdInline[] }) {
  return (
    <>
      {spans.map((s, i) => {
        if (s.type === "strong") {
          return (
            <strong key={i} className="font-semibold">
              {s.text}
            </strong>
          );
        }
        if (s.type === "em") {
          return <em key={i}>{s.text}</em>;
        }
        if (s.type === "code") {
          return (
            <code key={i} className="rounded bg-secondary px-1 py-0.5 text-[0.9em]">
              {s.text}
            </code>
          );
        }
        return <Fragment key={i}>{s.text}</Fragment>;
      })}
    </>
  );
}

function Blocks({ blocks }: { blocks: MdBlock[] }) {
  return (
    <>
      {blocks.map((b, i) => {
        if (b.type === "heading") {
          // Заголовок ответа — не заголовок страницы: уровень влияет на размер,
          // а не на структуру документа. Поэтому всегда один тег и класс по
          // уровню: h1 внутри пузыря чата спорил бы с заголовком страницы.
          return (
            <p
              key={i}
              className={
                b.level <= 2
                  ? "mt-3 text-sm font-semibold first:mt-0"
                  : "mt-3 text-sm font-medium first:mt-0"
              }
            >
              <Spans spans={b.spans} />
            </p>
          );
        }

        if (b.type === "list") {
          const cls = "mt-2 space-y-1 first:mt-0 " + (b.ordered ? "list-decimal" : "list-disc");
          const inner = b.items.map((item, k) => (
            // `pl-1` при `ml-5`: маркер стоит в отступе списка, а текст
            // начинается от него, а не вплотную.
            <li key={k} className="pl-1">
              <Spans spans={item.spans} />
              {item.children.length > 0 && <Blocks blocks={item.children} />}
            </li>
          ));
          return b.ordered ? (
            <ol key={i} start={b.start} className={`ml-5 ${cls}`}>
              {inner}
            </ol>
          ) : (
            <ul key={i} className={`ml-5 ${cls}`}>
              {inner}
            </ul>
          );
        }

        return (
          <p key={i} className="mt-2 whitespace-pre-line first:mt-0">
            <Spans spans={b.spans} />
          </p>
        );
      })}
    </>
  );
}

/**
 * Текст от модели → разметка.
 *
 * `children` намеренно нет: на вход идёт строка, и только строка. Узлы в
 * пропсе открыли бы дорогу готовой разметке из чужих рук.
 */
export function Markdown({ text }: { text: string }) {
  return <Blocks blocks={parseMarkdown(text)} />;
}
