/**
 * Разбор markdown, который пишет модель в чате (#28).
 *
 * ─── Почему не пакет ──────────────────────────────────────────────────────
 * Полный CommonMark нам не нужен и стоит дорого: `marked` разбирает таблицы,
 * ссылки, сноски и HTML, а потом эту строку HTML нужно чем-то обеззараживать
 * — то есть тянуть второй пакет (`dompurify`) и держать его настройку в
 * согласии с первым. Обеззараживание строки — это разбор чужого текста ради
 * того, чтобы отдать его обратно как разметку; ошибка в нём выглядит не как
 * кривой абзац, а как исполненный `<img onerror=…>` из ответа модели.
 *
 * Здесь разбор не производит HTML вовсе. На выходе данные — блоки и куски
 * текста; в разметку их превращает React, который экранирует текст сам и
 * по-другому не умеет. Дыре в экранировании тут негде появиться, потому что
 * экранирования тут нет.
 *
 * ─── Что поддерживается и почему именно это ───────────────────────────────
 * Набор взят с боевого, а не из спецификации: прогон 0092, ответ аналитика на
 * вопрос про ценность «крепкая семья». Там встретились ровно
 *
 *     **жирный**            — выделение термина, почти в каждом абзаце
 *     1.  пункт             — нумерованный список, два пробела после точки
 *         *   подпункт      — ненумерованный, отступ 4, три пробела за «*»
 *     пустая строка         — граница абзаца
 *
 * Добавлены соседи, которые модель пишет тем же почерком и которые ничего не
 * стоят: `*курсив*`, `_курсив_`, `` `код` `` и заголовки `#`. Ссылки, таблицы
 * и картинки не поддержаны намеренно — их в ответах нет, а поддержка ссылок
 * означала бы проверку схемы URL, то есть ещё одно место, где ошибка дорога.
 *
 * ─── Правило на весь файл ─────────────────────────────────────────────────
 * Незакрытая разметка — это текст. `5 * 3 = 15` не курсив, `snake_case` не
 * курсив, одинокая ** не съедает остаток ответа. Потерянный хвост ответа
 * выглядит как ответ, который модель не дописала, — то есть как чужая
 * поломка, и искать его будут не здесь.
 */

export type MdInline =
  | { type: "text"; text: string }
  | { type: "strong"; text: string }
  | { type: "em"; text: string }
  | { type: "code"; text: string };

export interface MdListItem {
  spans: MdInline[];
  /** Вложенные блоки пункта — обычно список второго уровня. Всегда массив. */
  children: MdBlock[];
}

export type MdBlock =
  | { type: "paragraph"; spans: MdInline[] }
  | { type: "heading"; level: number; spans: MdInline[] }
  | { type: "list"; ordered: boolean; start?: number; items: MdListItem[] };

/** Буква, цифра или подчёркивание — граница слова для `_курсива_`. */
const WORD = /[\p{L}\p{N}_]/u;

function isWord(ch: string): boolean {
  return ch.length > 0 && WORD.test(ch);
}

/**
 * Строка → куски текста с выделением.
 *
 * Проход один, слева направо. Каждый разделитель сначала ищет свою пару и
 * только найдя её становится разметкой; иначе символ уходит в текст как
 * обычный. Отсюда и берётся правило «незакрытое — это текст».
 */
export function parseInline(src: string): MdInline[] {
  const out: MdInline[] = [];
  let buf = "";

  function flush(): void {
    if (buf) {
      out.push({ type: "text", text: buf });
      buf = "";
    }
  }

  let i = 0;
  while (i < src.length) {
    const c = src[i];

    // `код` — первым: внутри него разметка не работает.
    if (c === "`") {
      const end = src.indexOf("`", i + 1);
      if (end > i + 1) {
        flush();
        out.push({ type: "code", text: src.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }

    // **жирный** — раньше курсива, иначе `**x**` прочтётся как пустой курсив.
    if (c === "*" && src[i + 1] === "*") {
      const end = src.indexOf("**", i + 2);
      if (end > i + 2) {
        flush();
        out.push({ type: "strong", text: src.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }

    if (c === "*" || c === "_") {
      // Открывать можно, если за знаком стоит не пробел: `5 * 3` не курсив.
      // Для `_` вдобавок нужна граница слова, иначе `snake_case_name`
      // распадётся на курсив посреди имени поля.
      const nextCh = src[i + 1] ?? "";
      const openable =
        nextCh !== "" && !/\s/.test(nextCh) && (c === "*" || !isWord(src[i - 1] ?? ""));

      if (openable) {
        let j = i + 1;
        let close = -1;
        while (j < src.length) {
          const k = src.indexOf(c, j);
          if (k < 0) break;
          const before = src[k - 1] ?? "";
          const after = src[k + 1] ?? "";
          const closable =
            k > i + 1 && !/\s/.test(before) && (c === "*" || !isWord(after));
          if (closable) {
            close = k;
            break;
          }
          j = k + 1;
        }
        if (close > 0) {
          flush();
          out.push({ type: "em", text: src.slice(i + 1, close) });
          i = close + 1;
          continue;
        }
      }
    }

    buf += c;
    i += 1;
  }

  flush();
  return out;
}

/** Пункт списка: отступ, маркер, номер (если он есть) и текст. */
const LIST_RE = /^(\s*)(?:([-*+])|(\d{1,9})[.)])[ \t]+(.*)$/;
const HEADING_RE = /^(#{1,6})[ \t]+(.+)$/;

/** Глубина вложенности, дальше которой разбор не идёт. */
const MAX_DEPTH = 6;

interface RawItem {
  text: string;
  childLines: string[];
}

/**
 * Собрать один список, начиная со строки `start`.
 *
 * Возвращает блок и номер строки, на которой список кончился.
 *
 * Уровень задаётся отступом ПЕРВОГО пункта. Строка с бо́льшим отступом
 * достаётся текущему пункту целиком — и вложенный список, и продолжение
 * абзаца разбираются потом, рекурсивно. Строка с меньшим отступом или с
 * другим типом маркера список закрывает: смена «1.» на «-» — это новый
 * список, а не продолжение прежнего.
 */
function parseList(lines: string[], start: number, depth: number): [MdBlock, number] {
  const head = LIST_RE.exec(lines[start]);
  // Вызывается только когда строка уже проверена, но сузить тип надо явно.
  if (!head) return [{ type: "paragraph", spans: parseInline(lines[start]) }, start + 1];

  const baseIndent = head[1].length;
  const ordered = head[3] !== undefined;
  const firstNumber = ordered ? Number(head[3]) : undefined;

  const raw: RawItem[] = [];
  let i = start;
  let cur: RawItem | null = null;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      // Пустая строка список не закрывает, если за ней снова пункт того же
      // уровня: модель разделяет пункты пустой строкой, и без этого «1.» и
      // «2.» стали бы двумя списками с нумерацией с единицы в каждом.
      let j = i + 1;
      while (j < lines.length && lines[j].trim() === "") j += 1;
      const ahead = j < lines.length ? LIST_RE.exec(lines[j]) : null;
      if (ahead && ahead[1].length >= baseIndent) {
        i = j;
        continue;
      }
      break;
    }

    const m = LIST_RE.exec(line);
    const indent = line.length - line.trimStart().length;

    if (m && m[1].length <= baseIndent) {
      if (m[1].length < baseIndent) break;
      if ((m[3] !== undefined) !== ordered) break;
      cur = { text: m[4], childLines: [] };
      raw.push(cur);
      i += 1;
      continue;
    }

    if (cur && indent > baseIndent) {
      cur.childLines.push(line);
      i += 1;
      continue;
    }

    break;
  }

  const items: MdListItem[] = raw.map((r) => ({
    spans: parseInline(r.text),
    children: depth < MAX_DEPTH ? parseBlocks(r.childLines, depth + 1) : [],
  }));

  const block: MdBlock =
    ordered && firstNumber !== undefined
      ? { type: "list", ordered: true, start: firstNumber, items }
      : { type: "list", ordered, items };

  return [block, i];
}

function parseBlocks(lines: string[], depth: number): MdBlock[] {
  const out: MdBlock[] = [];
  let para: string[] = [];

  function flushPara(): void {
    if (para.length === 0) return;
    const text = para.join("\n").trim();
    para = [];
    if (text) out.push({ type: "paragraph", spans: parseInline(text) });
  }

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      flushPara();
      i += 1;
      continue;
    }

    const h = HEADING_RE.exec(line.trim());
    if (h) {
      flushPara();
      out.push({ type: "heading", level: h[1].length, spans: parseInline(h[2].trim()) });
      i += 1;
      continue;
    }

    if (LIST_RE.test(line)) {
      flushPara();
      const [block, next] = parseList(lines, i, depth);
      out.push(block);
      // Защита от нулевого шага: список обязан съесть хотя бы свою строку.
      i = next > i ? next : i + 1;
      continue;
    }

    para.push(line);
    i += 1;
  }

  flushPara();
  return out;
}

/** Текст ответа модели → блоки. Разметки на выходе нет, только данные. */
export function parseMarkdown(src: string): MdBlock[] {
  if (!src || !src.trim()) return [];
  return parseBlocks(src.replace(/\r\n?/g, "\n").split("\n"), 0);
}
