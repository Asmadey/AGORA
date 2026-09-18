/**
 * Файл дополнительного контекста для синтетических персон (#31).
 *
 * ─── Что чинится ──────────────────────────────────────────────────────────
 * Зона выбора файла существовала и запоминала ИМЯ И РАЗМЕР. Содержимое не
 * читалось, никуда не отправлялось и ни во что не попадало, а подпись обещала
 * «pdf, docx, md, xlsx» — четыре формата, ни один из которых не обрабатывался.
 *
 * Со стороны это выглядело работающим: файл прикладывается, плашка появляется,
 * в резюме видно имя. Узнать, что персоны его не видели, можно было только по
 * ответам — то есть никак.
 *
 * ─── Два пути ─────────────────────────────────────────────────────────────
 * TXT и MD уже содержат текст и читаются браузером. PDF и XLS/XLSX уходят в
 * S3: извлечение требует библиотек воркера, а результат заранее неизвестен.
 * Оба пути сходятся в одном portrait.distill, поэтому файл уточняет лексику и
 * нишу, но не становится вторым источником соцдем-распределений.
 */

export const CONTEXT_TEXT_EXTENSIONS = [".txt", ".md"] as const;
export const CONTEXT_BINARY_EXTENSIONS = [".pdf", ".xlsx"] as const;

/**
 * Старый `.xls` принимается к выбору, но отклоняется с объяснением.
 *
 * Разбор таблиц в воркере делает `openpyxl`, а он читает только OOXML — то
 * есть `.xlsx`. Формат `.xls` — это BIFF, двоичный контейнер конца девяностых,
 * и для него нужна отдельная библиотека.
 *
 * Убрать `.xls` из `accept` было бы хуже, чем отклонить: файл просто не
 * выбрался бы в диалоге, и человек решил бы, что дело в самом файле. Здесь он
 * узнаёт настоящую причину и что с ней делать — пересохранить, это одно
 * действие в Excel.
 *
 * Отказ выдаётся СРАЗУ, в браузере. Принять `.xls` и упасть в воркере значило
 * бы узнать о непригодности файла после запуска, за который уже заплачено.
 */
export const CONTEXT_LEGACY_SPREADSHEET = ".xls";
export const CONTEXT_EXTENSIONS = [
  ...CONTEXT_TEXT_EXTENSIONS,
  ...CONTEXT_BINARY_EXTENSIONS,
] as const;

export type ContextFileProcessing = "browser" | "worker";

export interface ContextFileSelection {
  name: string;
  size: number;
  /** Заполнено для txt/md; у бинарного файла текст появляется только в воркере. */
  text?: string;
  /** Строка audience_context_files для pdf/xls/xlsx. */
  id?: string;
  processing: ContextFileProcessing;
}

/** Значение для `accept` у input[type=file]. */
export const CONTEXT_ACCEPT = [
  ...CONTEXT_EXTENSIONS,
  "text/plain",
  "text/markdown",
  "application/pdf",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
].join(",");

export const CONTEXT_FILE_MAX_BYTES = 50 * 1024 * 1024;

export function isTextContextFile(name: string): boolean {
  const lower = (name ?? "").toLowerCase();
  return CONTEXT_TEXT_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export function contextMimeType(name: string): string {
  const lower = (name ?? "").toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".xls")) return "application/vnd.ms-excel";
  if (lower.endsWith(".xlsx")) {
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  }
  if (lower.endsWith(".md")) return "text/markdown";
  return "text/plain";
}

/**
 * Потолок в символах — 4000.
 *
 * ─── Откуда число ─────────────────────────────────────────────────────────
 * Контекст уезжает в системный промпт КАЖДОЙ персоны и оплачивается на каждом
 * вызове. Арифметика на боевом прогоне 0051:
 *
 *   * промпт персоны и так ≈ 83 000 символов (≈ 36 000 токенов);
 *   * русский текст — примерно 2,7 символа на токен, значит 4000 символов
 *     это ≈ 1500 токенов;
 *   * 27 персон при перекрытии ×3 — 81 вызов, то есть ≈ 121 000 токенов за
 *     прогон. При общем расходе около 2,8 млн токенов это ~4 %.
 *
 * Владелец предлагал 2000. Вдвое больший потолок стоит тех же четырёх
 * процентов вместо двух и позволяет вместить осмысленную заметку об аудитории,
 * а не три предложения. Дальше расти незачем: файл — это уточнение лексики и
 * специфики ниши, а не документ. Контекстное окно модели тут не ограничитель —
 * ограничитель цена, помноженная на число персон.
 */
export const CONTEXT_LIMIT_CHARS = 4000;

export type ContextConflictKind = "demographics" | "scores";

export interface ContextConflict {
  kind: ContextConflictKind;
  evidence: string;
}

/**
 * Находит указания, которые выглядят как попытка задать заземлённые поля.
 *
 * Это намеренно проверка текста, а не пересчёт корпуса в браузере: корпусная
 * истина живёт на сервере. Пользователю достаточно заранее сказать, что файл
 * содержит спорное указание; окончательные доли и средние оценки всё равно
 * остаются за генератором по корпусу.
 */
export function detectContextConflicts(text: string): ContextConflict[] {
  const body = normalizeContext(text);
  if (!body) return [];

  const conflicts: ContextConflict[] = [];
  // Одних слов «аудитория» и «города» недостаточно: это обычное описание
  // ниши. Спор начинается только там, где файл задаёт число, которое продукт
  // считает сам. Паттерны намеренно консервативны: лучше не показать редкое
  // предупреждение, чем превратить каждое содержательное описание в фон.
  const number = String.raw`(?:\d{1,3}(?:[.,]\d+)?|\d{1,3}\s*[-\u2013\u2014]\s*\d{1,3}|\d{1,3}\s*\+)`;
  const demographicTerm =
    String.raw`(?:женщин|мужчин|женск\w*|мужск\w*|возраст\w*|москв\w*|петербург\w*|столиц\w*|регион\w*|город\w*)`;
  const demographicClaim = new RegExp(
    String.raw`(?:${number}\s*%?\s*${demographicTerm}|${demographicTerm}[^\n]{0,24}${number}\s*%?)`,
    "i",
  ).test(body);
  if (demographicClaim) {
    conflicts.push({
      kind: "demographics",
      evidence: "конкретные доли или числа соцдема",
    });
  }

  const scoreTerm = String.raw`(?:оценк\w*|балл\w*|рейтинг\w*|score|средн\w*\s+(?:балл\w*|оценк\w*))`;
  const scoreClaim = new RegExp(
    String.raw`(?:${scoreTerm}[^\n]{0,30}${number}|${number}[^\n]{0,30}${scoreTerm})`,
    "i",
  ).test(body);
  if (scoreClaim) {
    conflicts.push({ kind: "scores", evidence: "конкретные оценки или баллы" });
  }

  return conflicts;
}

/** Спокойное правило работы, которое показывается при любом вложении. */
export function contextGroundingNote(): string {
  return (
    "Распределения по соцдему и калибровка баллов берутся из grounding-корпуса. " +
    "Файл уточняет язык, интересы и специфику ниши, но не переопределяет эти расчёты."
  );
}

/** Текст предупреждения рядом с приложенным файлом либо null. */
export function contextConflictWarning(text: string): string | null {
  const conflicts = detectContextConflicts(text);
  if (conflicts.length === 0) return null;
  return (
    "Предупреждение: файл задаёт " +
    conflicts.map((conflict) => conflict.evidence).join(" и ") +
    ", а это продукт считает по grounding-корпусу. Указание будет разрешено " +
    "в пользу корпуса."
  );
}

/**
 * Текст без краевых пробелов и без длинных пустот.
 *
 * Считать лимит по сырому файлу нечестно: файл из тысячи переводов строк
 * отвергался бы за объём, которого в модель не поедет.
 */
export function normalizeContext(text: string): string {
  return (text ?? "")
    .replace(/\r\n?/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Претензия к файлу либо null, если он годится. */
export function contextFileError(
  name: string,
  text?: string,
  sizeBytes?: number,
): string | null {
  const lower = (name ?? "").toLowerCase();
  if (lower.endsWith(CONTEXT_LEGACY_SPREADSHEET)) {
    return (
      "формат .xls не читается: пересохраните таблицу как .xlsx " +
      "(в Excel — «Сохранить как» → «Книга Excel»)"
    );
  }
  if (!CONTEXT_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return `принимаются только ${CONTEXT_EXTENSIONS.join(" и ")}`;
  }

  if (sizeBytes !== undefined && sizeBytes > CONTEXT_FILE_MAX_BYTES) {
    return (
      `файл весит ${Math.ceil(sizeBytes / 1024 / 1024)} МБ при потолке ` +
      `${CONTEXT_FILE_MAX_BYTES / 1024 / 1024} МБ`
    );
  }

  if (!isTextContextFile(name)) {
    // Для PDF/XLS содержимое появится только после разбора в воркере. Проверять
    // его как браузерный текст означало бы объявить любой бинарный файл пустым.
    return null;
  }

  const body = normalizeContext(text ?? "");
  if (!body) {
    // Молча принятый пустой файл выглядит как приложенный контекст, которого нет.
    return "файл пуст — прикладывать нечего";
  }

  if (body.length > CONTEXT_LIMIT_CHARS) {
    return (
      `${body.length} символов при потолке ${CONTEXT_LIMIT_CHARS}: ` +
      `контекст уходит в промпт каждой персоны и оплачивается на каждом вызове`
    );
  }
  return null;
}
