/**
 * Перезапуск исследования с теми же персонами (#30).
 *
 * ─── Что чинится ──────────────────────────────────────────────────────────
 * Кнопка «Перезапустить» вела на `/studies/new?rerun=<id>`, а параметр `rerun`
 * не разбирался нигде: визард открывался пустым. Нажавший её заново загружал
 * тот же файл и заново набирал аудиторию — то есть получал не перезапуск, а
 * новое исследование, которое не с чем сравнить.
 *
 * ─── Что переносится и что нет ────────────────────────────────────────────
 * Переносятся материал, набор персон и настройки прогона. Анкета — НЕТ: ради
 * новых вопросов перезапуск и делают. Разница в ответах тогда объясняется
 * вопросами, а не другим набором персон и не другой расшифровкой.
 *
 * ─── Почему предупреждение, а не отказ ────────────────────────────────────
 * Прогон без сохранённого набора персон перезапустить «с теми же персонами»
 * нельзя: аудитория собиралась на лету и нигде не лежит. Молча собрать новых
 * значило бы подменить смысл кнопки, а запретить — оставить человека без
 * объяснения. Поэтому визард открывается, но говорит, чего именно не хватает.
 */

export interface SourceRun {
  id: string;
  mode: string | null;
  videoRef: string | null;
  sourceName: string | null;
  personaSetId: string | null;
  projectId: string | null;
  replicationCount: number | null;
  whisperModel: string | null;
  title: string | null;
}

export interface RerunPrefill {
  mode: "short" | "long";
  videoRef: string | null;
  sourceName: string | null;
  personaSetId: string | null;
  projectId: string | null;
  replicationCount: number;
  whisperModel: string | null;
  /** Анкета всегда пустая: см. докстринг модуля. */
  surveyQuestions: never[];
  title: string;
  parentTaskId: string;
  /** По умолчанию безопасная изоляция; пользователь меняет это до запуска. */
  memoryMode: "interrogation" | "clean";
  carryOverMemory: boolean;
  /** Чего не хватает для честного повтора. null — всё на месте. */
  warning: string | null;
}

export interface ScoreChange {
  key: string;
  parent: number | null;
  current: number | null;
  delta: number | null;
}

/**
 * Сравнение чисел отчётов живёт в lib, а не в странице: иначе экран мог бы
 * показывать «без изменений» по одной трактовке null и 0, а экспорт - по
 * другой. Отсутствующий балл остаётся null и не превращается в искусственный
 * ноль.
 */
export function compareScoreMaps(
  current: Record<string, number | null>,
  parent: Record<string, number | null>,
): ScoreChange[] {
  const keys = [...new Set([...Object.keys(parent), ...Object.keys(current)])].sort();
  return keys.flatMap((key) => {
    const parentValue = parent[key] ?? null;
    const currentValue = current[key] ?? null;
    if (parentValue === currentValue) return [];
    return [{
      key,
      parent: parentValue,
      current: currentValue,
      delta:
        parentValue !== null && currentValue !== null
          ? currentValue - parentValue
          : null,
    }];
  });
}

export function rerunPrefill(source: SourceRun): RerunPrefill {
  const missing: string[] = [];
  if (!source.personaSetId) {
    missing.push(
      "у исходного прогона не сохранён набор персон — аудиторию придётся собрать заново, " +
        "и это будут другие персоны",
    );
  }
  if (!source.videoRef) {
    missing.push("у исходного прогона не записан материал — ролик придётся загрузить заново");
  }

  return {
    mode: source.mode === "long" ? "long" : "short",
    videoRef: source.videoRef,
    sourceName: source.sourceName,
    personaSetId: source.personaSetId,
    projectId: source.projectId,
    replicationCount: source.replicationCount ?? 1,
    whisperModel: source.whisperModel,
    surveyQuestions: [],
    title: rerunTitle(source),
    parentTaskId: source.id,
    memoryMode: "clean",
    carryOverMemory: false,
    warning: missing.length > 0 ? missing.join("; ") : null,
  };
}

/**
 * Название повтора: «<исходное> — повтор».
 *
 * Подсказка, а не обязанность: поле остаётся правимым. Без пометки два
 * исследования с одинаковым именем различались бы только номером, и выбрать
 * нужное в списке было бы нельзя.
 */
function rerunTitle(source: SourceRun): string {
  const base = (source.title || source.sourceName || "Исследование").trim();
  return `${base} — повтор`;
}
