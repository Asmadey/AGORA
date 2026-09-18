import assert from "node:assert/strict";
import { test } from "node:test";

import type { SurveyQuestion } from "./agora-types.ts";
import { newQuestionDraft } from "./survey-composition.ts";
import {
  addOption,
  addRow,
  draftForType,
  draftIssues,
  removeOption,
  removeRow,
  setOptionLabel,
  setRowLabel,
} from "./survey-draft.ts";

/**
 * Черновик своего вопроса оператора: варианты, строки и что мешает сохранить.
 *
 * ─── Дыра, которую это закрывает ───────────────────────────────────────────
 * Конструктор предлагал пять типов вопроса, но добавить варианты ответа было
 * НЕЧЕМ: при выборе «Один из списка», «Несколько из списка» или «Матрица»
 * форма показывала только подпись типа и кнопку «Готово». То есть закрытый
 * вопрос создать было нельзя вообще — а валидатор требует у такого вопроса не
 * меньше двух вариантов, и матрице ещё и строку.
 *
 * Оператор при этом ничего не узнавал: кнопка «Готово» была активна, вопрос
 * добавлялся, и отказ приходил позже, от сервера, на сохранении всей анкеты.
 *
 * ─── Почему логика здесь, а не в компоненте ────────────────────────────────
 * Веб-тесты собирают только `lib/**`. Это третий раз за день, когда логика,
 * оставленная в `.tsx`, оказывалась непокрытой: сначала разошлась проверка
 * заземления, потом уцелела третья точка засева анкеты.
 */

const draft = (type: SurveyQuestion["type"]) =>
  draftForType(newQuestionDraft("q-1"), type);

test("смена типа готовит вопрос к заполнению, а не оставляет его пустым", () => {
  const single = draft("single_choice");
  assert.ok(
    (single.options?.length ?? 0) >= 2,
    "закрытому вопросу нужно не меньше двух вариантов — оператор не должен " +
      "узнавать об этом от сервера при сохранении анкеты",
  );
  assert.equal(single.scaleMin, undefined, "у выбора из списка шкалы нет и быть не может");
  assert.equal(single.scaleMax, undefined);

  const matrix = draft("matrix_single");
  assert.ok((matrix.options?.length ?? 0) >= 2);
  assert.ok((matrix.rows?.length ?? 0) >= 1, "матрице нужна хотя бы одна строка");

  const open = draft("open");
  assert.equal(open.options, undefined, "у открытого вопроса вариантов нет");
  assert.equal(open.rows, undefined);
});

test("возврат к шкале восстанавливает границы и убирает варианты", () => {
  const back = draftForType(draft("matrix_single"), "scale");

  assert.equal(back.options, undefined);
  assert.equal(back.rows, undefined);
  assert.equal(typeof back.scaleMin, "number");
  assert.equal(typeof back.scaleMax, "number");
});

test("удаление варианта не освобождает его идентификатор для нового", () => {
  /**
   * Ответ персоны адресует вариант идентификатором. Если удалить второй вариант
   * и добавить новый, получив тот же `o-2`, то ответы прошлого прогона на
   * удалённый вариант зачтутся новому — и различить это в отчёте будет нечем.
   */
  let q = draft("single_choice");
  const first = q.options?.[0].id;
  q = addOption(q);
  const third = q.options?.at(-1)?.id;

  q = removeOption(q, third!);
  q = addOption(q);

  assert.notEqual(q.options?.at(-1)?.id, third, "идентификатор удалённого варианта переиспользован");
  assert.equal(q.options?.[0].id, first, "уцелевшие варианты сменили идентификаторы");
});

test("подписи правятся, а идентификаторы — нет", () => {
  let q = draft("single_choice");
  const id = q.options![0].id;

  q = setOptionLabel(q, id, "Скорее да");
  assert.equal(q.options![0].label, "Скорее да");
  assert.equal(q.options![0].id, id, "правка подписи сменила идентификатор варианта");

  let m = draft("matrix_single");
  const rowId = m.rows![0].id;
  m = setRowLabel(m, rowId, "Герой вызывает сочувствие");
  assert.equal(m.rows![0].label, "Герой вызывает сочувствие");
  assert.equal(m.rows![0].id, rowId);
});

test("строки матрицы добавляются и удаляются по тем же правилам", () => {
  let q = addRow(draft("matrix_single"));
  assert.equal(q.rows?.length, 2);

  const removed = q.rows![1].id;
  q = removeRow(q, removed);
  q = addRow(q);
  assert.notEqual(q.rows?.at(-1)?.id, removed);
});

test("что мешает сохранить вопрос — по строке на причину", () => {
  assert.deepEqual(draftIssues({ ...draft("scale"), label: "Насколько понравилось?" }), []);

  assert.ok(
    draftIssues(draft("scale")).some((r) => /формулировк/i.test(r)),
    "пустая формулировка должна называться причиной",
  );

  const named = (q: SurveyQuestion) => ({ ...q, label: "Вопрос" });

  assert.ok(
    draftIssues({ ...named(draft("scale")), scaleMin: 10, scaleMax: 10 }).length > 0,
    "вырожденная шкала должна называться причиной",
  );

  const oneOption = named(draft("single_choice"));
  assert.ok(
    draftIssues(removeOption(oneOption, oneOption.options![0].id)).some((r) =>
      /двух вариантов/i.test(r),
    ),
  );

  const blank = named(draft("single_choice"));
  assert.ok(
    draftIssues(blank).some((r) => /подпис/i.test(r)),
    "вариант без подписи должен называться причиной: валидатор такой анкеты не примет",
  );

  const emptyMatrix = named(draft("matrix_single"));
  assert.ok(
    draftIssues(removeRow(emptyMatrix, emptyMatrix.rows![0].id)).some((r) => /строк/i.test(r)),
  );
});

test("потолок выбора не может быть больше числа вариантов", () => {
  const q = { ...draft("multi_choice"), label: "Вопрос", maxChoices: 9 };
  assert.ok(
    draftIssues(q).some((r) => /потолок|вариантов/i.test(r)),
    "потолок «до 9 ответов» при трёх вариантах — это обещание, которого анкета " +
      "не выполнит, и заметить его в отчёте будет нечем",
  );
});

test("заполненный черновик принимается валидатором", async () => {
  const { validateSurvey } = await import("./server/survey-validator.ts");

  let q = { ...draft("multi_choice"), label: "Что понравилось больше всего?" };
  q = setOptionLabel(q, q.options![0].id, "Сюжет");
  q = setOptionLabel(q, q.options![1].id, "Музыка");
  q = { ...q, maxChoices: 2 };

  assert.deepEqual(draftIssues(q), []);

  const { DEFAULT_QUESTIONS } = await import("./survey-composition.ts");
  const result = validateSurvey({ name: "Проверка", questions: [...DEFAULT_QUESTIONS, q] });

  assert.deepEqual(
    result.errors,
    [],
    "редактор собрал вопрос, который сервер откажется сохранять",
  );
});
