import type { SurveyQuestion } from "./agora-types";

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
