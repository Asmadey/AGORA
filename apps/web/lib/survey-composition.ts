import type { SurveyQuestion } from "./agora-types";
import {
  MANDATORY_QUESTIONS,
  themesOf,
  withSelectedThemes,
} from "./customer-survey.ts";

/**
 * Состав анкеты: базовые критерии, проверка заземления и заготовка своего вопроса.
 *
 * ─── Почему это не в компоненте ────────────────────────────────────────────
 * Раньше состав жил прямо в `SurveyBuilder.tsx`, и там же стояла проверка
 * заземления. Компонент невозможно прогнать `node --test` (веб-тесты собирают
 * только `lib/**`), поэтому проверка не была покрыта ничем — и разошлась.
 *
 * Базовым критериям решением владельца от 17.09.2026 запрещена любая шкала,
 * кроме 0–10. Константы перевели, схему перевели, валидатор перевели, промпт
 * перевели. А проверку — нет:
 *
 *     base.some((q) => q.type !== "scale" || q.scaleMin !== 1 || q.scaleMax !== 10)
 *
 * Отказа при этом не возникало: у оператора на ЛЮБОЙ правильной анкете горело
 * предупреждение «заземление сломано», а кнопка восстановления предлагала
 * вернуть то, что и так стоит. Дефект выглядел придиркой интерфейса.
 *
 * Поэтому здесь нет ни одного числа шкалы. `groundingIssues` сверяется с теми
 * вопросами, которые продукт сам и предлагает, а `newQuestionDraft` берёт
 * границы оттуда же. Скопировать число больше неоткуда.
 */

/**
 * Пять базовых критериев в исходном виде.
 *
 * Подписи короткие намеренно: их читает оператор в списке вопросов и человек
 * в отчёте, а длинные формулировки заказчика приезжают отдельно вместе с
 * обязательным блоком (`MANDATORY_QUESTIONS`), где у тех же пяти критериев
 * стоят его собственные тексты.
 */
export const BASE_QUESTIONS: SurveyQuestion[] = [
  { id: "base-1", baseKey: "overall_impression", label: "Общее впечатление", type: "scale", scaleMin: 0, scaleMax: 10 },
  { id: "base-2", baseKey: "plot", label: "Сюжет", type: "scale", scaleMin: 0, scaleMax: 10 },
  { id: "base-3", baseKey: "acting", label: "Актёрская игра", type: "scale", scaleMin: 0, scaleMax: 10 },
  { id: "base-4", baseKey: "music", label: "Музыка", type: "scale", scaleMin: 0, scaleMax: 10 },
  { id: "base-5", baseKey: "cinematography", label: "Операторская работа", type: "scale", scaleMin: 0, scaleMax: 10 },
];

/** Шкала базовых критериев — читается у них самих, а не объявляется рядом. */
const BASE_SCALE = {
  min: BASE_QUESTIONS[0].scaleMin,
  max: BASE_QUESTIONS[0].scaleMax,
};

/**
 * Подпись шкалы для текста на экране.
 *
 * Оператору про шкалу рассказывают три абзаца в конструкторе, и до этой правки
 * все три называли её числами прямо в тексте. Прозу проверка типов не
 * охраняет: константы ушли на 0–10, а экран ещё полдня объяснял, почему важна
 * шкала 1–10. Подпись собирается из тех же значений, что и сами вопросы.
 */
export const BASE_SCALE_LABEL = `${BASE_SCALE.min}–${BASE_SCALE.max}`;

/**
 * Что в анкете мешает заземлению — по одной внятной строке на причину.
 *
 * Пустой массив значит «всё в порядке». Список, а не булево: оператору нужно
 * знать, какой именно критерий сломан, иначе предупреждение нечем закрыть.
 *
 * Подпись критерия сюда не входит: переименование — законное право оператора,
 * заземление держится на `baseKey`, типе и шкале.
 */
export function groundingIssues(questions: SurveyQuestion[]): string[] {
  const issues: string[] = [];

  for (const original of BASE_QUESTIONS) {
    const present = questions.find((q) => q.baseKey === original.baseKey);

    if (!present) {
      issues.push(`критерий «${original.label}» удалён из анкеты`);
      continue;
    }
    if (present.type !== original.type) {
      issues.push(`критерий «${present.label}» перестал быть шкалой`);
      continue;
    }
    if (present.scaleMin !== original.scaleMin || present.scaleMax !== original.scaleMax) {
      issues.push(
        `у критерия «${present.label}» шкала ${present.scaleMin}–${present.scaleMax}, ` +
          `а заземление считается по ${original.scaleMin}–${original.scaleMax}`,
      );
    }
  }

  return issues;
}

/**
 * Заготовка своего вопроса оператора.
 *
 * Шкала — та же, что у базовых критериев. Иначе в одной анкете оказались бы
 * две разные десятибалльные шкалы, и различить их в отчёте было бы нечем:
 * «7» на 1–10 и «7» на 0–10 — разные доли одного и того же диапазона.
 */
export function newQuestionDraft(id: string): SurveyQuestion {
  return {
    id,
    label: "",
    type: "scale",
    scaleMin: BASE_SCALE.min,
    scaleMax: BASE_SCALE.max,
  };
}

// ─── Обязательный блок заказчика ──────────────────────────────────────────

/** Идентификаторы всех тем вопроса-матрицы: состояние «выбрано всё». */
export const MANDATORY_THEME_IDS: string[] = themesOf(9).map((t) => t.id);

/** Доступные оператору темы вопроса 9, каждая целиком со своими строками. */
export const MANDATORY_THEMES = themesOf(9);

/** Подпись чипа с количеством выбранных тем вопроса 9. */
export function mandatoryThemeCountLabel(count: number): string {
  const lastDigit = count % 10;
  const lastTwoDigits = count % 100;
  let noun = "тем";

  if (lastDigit === 1 && lastTwoDigits !== 11) {
    noun = "тема";
  } else if (
    lastDigit >= 2 &&
    lastDigit <= 4 &&
    (lastTwoDigits < 12 || lastTwoDigits > 14)
  ) {
    noun = "темы";
  }

  return `${count} ${noun}`;
}

export type ThemeToggleResult = {
  selected: string[];
  reason?: string;
};

/** Переключает тему, не позволяя обязательному блоку стать пустым. */
export function toggleMandatoryTheme(selected: string[], themeId: string): ThemeToggleResult {
  const current = new Set(selected);
  if (current.has(themeId) && current.size === 1) {
    return { selected: [...selected], reason: "Нельзя снять последнюю тему." };
  }

  if (current.has(themeId)) current.delete(themeId);
  else current.add(themeId);

  return {
    selected: MANDATORY_THEME_IDS.filter((id) => current.has(id)),
  };
}

const MANDATORY_IDS = new Set(MANDATORY_QUESTIONS.map((q) => q.id));

/**
 * Вопрос пришёл из обязательного блока заказчика?
 *
 * По идентификатору, а не по номеру: номер у своих вопросов оператора тоже
 * появится, когда конструктор их пронумерует, и различать по нему станет нечем.
 */
export function isMandatory(question: SurveyQuestion): boolean {
  return MANDATORY_IDS.has(question.id);
}

/**
 * Состав анкеты: сколько вопросов обязательные, сколько добавил оператор.
 *
 * ─── Почему по `isMandatory`, а не по отсутствию `baseKey` ────────────────
 * Оба места, где этот счёт показывался, считали своим любой вопрос без
 * `baseKey`. Пока обязательными были те самые пять базовых критериев, ответ
 * совпадал: не базовый — значит свой.
 *
 * С 17.09.2026 обязательный блок — пятнадцать вопросов заказчика, и `baseKey`
 * несут только первые пять. Остальные десять предикат записывал в «свои», и
 * свежесозданная анкета, в которую оператор не добавил ни одного вопроса,
 * показывала «10 своих».
 *
 * Считать вычитанием длины базового набора тоже нельзя, и это прежняя причина,
 * которая не отменяется: базовый вопрос можно снять, и тогда три своих вопроса
 * при двух снятых базовых давали «5 вопросов» без единого упоминания своих.
 *
 * Правильный признак один — членство в обязательном блоке по идентификатору.
 * Он же лежит в `isMandatory` и уже используется конструктором.
 */
export function surveyComposition(questions: SurveyQuestion[]): {
  total: number;
  mandatory: number;
  custom: number;
} {
  const mandatory = questions.filter(isMandatory).length;
  return { total: questions.length, mandatory, custom: questions.length - mandatory };
}

/**
 * Анкета целиком: обязательный блок заказчика, затем вопросы оператора.
 *
 * Порядок не косметика. Пятнадцать обязательных вопросов пронумерованы
 * заказчиком, отчёт и выгрузка называют их этими номерами, и его собственный
 * полевой файл идёт в том же порядке. Свои вопросы оператора приходят после.
 *
 * Обязательный блок несёт все пять базовых критериев (вопросы 1–5 заказчика),
 * поэтому отдельно добавлять `BASE_QUESTIONS` не нужно: получилось бы по два
 * вопроса на каждый `baseKey`, и заземление считалось бы дважды.
 *
 * Свои вопросы с идентификатором из обязательного блока отбрасываются: иначе
 * сохранённая анкета, собранная до этой правки, дала бы дубликат id, и
 * валидатор отверг бы её целиком — на экране это выглядело бы как «анкета
 * сломалась сама».
 */
export function withMandatory(
  custom: SurveyQuestion[],
  themeIds: string[],
): SurveyQuestion[] {
  const mandatory = withSelectedThemes(themeIds);
  const taken = new Set(mandatory.map((q) => q.id));
  return [...mandatory, ...custom.filter((q) => !taken.has(q.id))];
}

/**
 * Собирает обязательный блок после изменения выбора тем.
 *
 * Темы переключаются только целиком: вместе с вопросом 9 меняется и его
 * зависимый вопрос 11. Пустой список намеренно не запрещается здесь, чтобы
 * чистая функция могла описать промежуточное состояние; интерфейс не даёт
 * снять последнюю галочку и объясняет причину оператору на месте.
 */
export function withSelectedMandatoryThemes(
  questions: SurveyQuestion[],
  themeIds: string[],
): SurveyQuestion[] {
  return withMandatory(questions.filter((q) => !isMandatory(q)), themeIds);
}

/**
 * С чего начинается новая анкета.
 *
 * Все десять тем вопроса 9 включены: решение владельца 17.09.2026 — обязательные
 * пятнадцать не выключаются, гибкость оператора в выборе тем и в своих вопросах.
 * Полный состав измерен на боевом (67 полей, 20 персон, 100 % покрытия), то есть
 * это не теоретический максимум, а проверенное состояние.
 */
export const DEFAULT_QUESTIONS: SurveyQuestion[] = withMandatory([], MANDATORY_THEME_IDS);
