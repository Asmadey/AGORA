import assert from "node:assert/strict";
import { test } from "node:test";

import type { SurveyQuestion } from "./agora-types.ts";
import { newQuestionDraft } from "./survey-composition.ts";
import {
  addOption,
  addRow,
  addRowOption,
  addRowTo,
  addTheme,
  draftForType,
  draftIssues,
  removeOption,
  removeRow,
  removeRowOption,
  removeTheme,
  rowOptions,
  setOptionLabel,
  setRowLabel,
  setRowMaxChoices,
  setRowOptionLabel,
  setThemeLabel,
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
  assert.ok((matrix.rows?.length ?? 0) >= 1, "матрице нужна хотя бы одна строка");
  assert.ok(
    (matrix.rows![0].options?.length ?? 0) >= 2,
    "варианты живут у вопроса матрицы, а не у матрицы целиком",
  );
  assert.equal(
    matrix.options,
    undefined,
    "общий список вариантов у своей матрицы оператора не заводится: у вопросов " +
      "внутри темы они разные, и общий склеил бы их в один",
  );

  const open = draft("open");
  assert.equal(open.options, undefined, "у открытого вопроса вариантов нет");
  assert.equal(open.rows, undefined);
});

test("возврат к шкале восстанавливает границы и убирает варианты", () => {
  const back = draftForType(draft("matrix_single"), "scale");

  assert.equal(back.options, undefined);
  assert.equal(back.rows, undefined);
  assert.equal(back.themes, undefined);
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
  assert.ok(
    (q.rows![1].options?.length ?? 0) >= 2,
    "новый вопрос матрицы приходит пустым: заполнить его нечем, а на вид он " +
      "не отличается от сломанного",
  );

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

// ─── Матрица как дерево: тема → вопросы → общие варианты ──────────────────

test("матрица заводится темой с вопросом внутри, а не голой строкой", () => {
  const m = draft("matrix_single");

  assert.ok((m.themes?.length ?? 0) >= 1, "у матрицы должна быть хотя бы одна тема");
  assert.ok((m.rows?.length ?? 0) >= 1);
  assert.equal(
    m.rows![0].themeId,
    m.themes![0].id,
    "вопрос не привязан к теме — в отчёте его не с чем будет сгруппировать",
  );
});

test("удаление темы уносит её вопросы", () => {
  let m = draft("matrix_single");
  m = addTheme(m);
  m = addRowTo(m, m.themes![1].id);

  const doomed = m.themes![0].id;
  const kept = m.themes![1].id;
  m = removeTheme(m, doomed);

  assert.equal(m.themes?.length, 1);
  assert.ok(
    m.rows?.every((r) => r.themeId === kept),
    "остались вопросы удалённой темы: они не попадут ни в одну группу отчёта " +
      "и молча выпадут из интегрального показателя",
  );
});

test("у каждого вопроса темы свой список вариантов", () => {
  /**
   * Общий список был перенесён на матрицу вообще из частного случая вопроса 9
   * заказчика, где он действительно один на сорок три подтемы. У своей матрицы
   * оператора вопросы внутри темы разные: «Гордость за страну» отвечается
   * «поднималась / не поднималась», а «Что запомнилось» — «финал / музыка».
   * Общий список предложил бы персоне музыку там, где спрашивают про гордость.
   */
  let m = draft("matrix_single");
  m = addTheme(m);
  const [first, second] = m.rows!;

  m = setRowOptionLabel(m, first.id, first.options![0].id, "Поднималась");
  m = setRowOptionLabel(m, second.id, second.options![0].id, "Финал");

  assert.equal(rowOptions(m, m.rows![0])[0].label, "Поднималась");
  assert.equal(rowOptions(m, m.rows![1])[0].label, "Финал", "правка задела чужой вопрос");
});

test("варианты вопроса добавляются и удаляются, не задевая соседний вопрос", () => {
  let m = draft("matrix_single");
  m = addRowTo(m, m.themes![0].id);
  const [first, second] = m.rows!;

  m = addRowOption(m, second.id);
  assert.equal(rowOptions(m, m.rows![1]).length, 3);
  assert.equal(rowOptions(m, m.rows![0]).length, 2, "добавление задело соседний вопрос");

  const doomed = rowOptions(m, m.rows![1])[2].id;
  m = removeRowOption(m, second.id, doomed);
  m = addRowOption(m, second.id);
  assert.notEqual(
    rowOptions(m, m.rows![1]).at(-1)!.id,
    doomed,
    "идентификатор удалённого варианта переиспользован",
  );
  assert.equal(rowOptions(m, m.rows![0]).length, 2);
  void first;
});

test("сколько вариантов нельзя задать больше, чем их добавлено", () => {
  /**
   * Поле «сколько вариантов» — это обещание персоне, а не подпись. Потолок «до
   * трёх» при двух добавленных вариантах анкета не выполнит, и заметить это в
   * отчёте будет нечем: доли сойдутся по тем двум, что есть.
   */
  let m = draft("matrix_single");
  const row = m.rows![0];

  m = setRowMaxChoices(m, row.id, 5);
  assert.equal(m.rows![0].maxChoices, 2, "потолок не прижат к числу вариантов");

  m = addRowOption(m, row.id);
  m = setRowMaxChoices(m, row.id, 3);
  assert.equal(m.rows![0].maxChoices, 3);

  m = setRowMaxChoices(m, row.id, 0);
  assert.equal(m.rows![0].maxChoices, 1, "ноль ответов означает вопрос без ответа");
});

test("удаление варианта опускает потолок следом за ним", () => {
  /**
   * Иначе потолок пережил бы вариант, на который был рассчитан: «до трёх» при
   * двух оставшихся — та же невыполнимая анкета, только собранная в два шага.
   */
  let m = draft("matrix_single");
  const row = m.rows![0];
  m = addRowOption(m, row.id);
  m = setRowMaxChoices(m, row.id, 3);

  m = removeRowOption(m, row.id, rowOptions(m, m.rows![0])[2].id);
  assert.equal(m.rows![0].maxChoices, 2);
});

test("вопрос матрицы без вариантов и без подписей назван причиной", () => {
  const named = (q: SurveyQuestion) => ({ ...q, label: "Вопрос" });
  let m = named(draft("matrix_single"));
  m = setThemeLabel(m, m.themes![0].id, "Патриотизм");
  m = setRowLabel(m, m.rows![0].id, "Гордость за страну");

  assert.ok(
    draftIssues(m).some((r) => /подпис/i.test(r)),
    "вариант без подписи должен называться причиной",
  );

  const row = m.rows![0];
  m = setRowOptionLabel(m, row.id, row.options![0].id, "Поднималась");
  m = setRowOptionLabel(m, row.id, row.options![1].id, "Не поднималась");
  assert.deepEqual(draftIssues(m), []);

  const bare = removeRowOption(m, row.id, row.options![1].id);
  assert.ok(
    draftIssues(bare).some((r) => /двух вариантов/i.test(r)),
    "вопрос с одним вариантом — это не выбор, и сервер такую анкету отвергнет",
  );
});

/** Подписать варианты одного вопроса матрицы: без подписей жалуется валидатор. */
function fillRow(question: SurveyQuestion, rowId: string): SurveyQuestion {
  const row = question.rows!.find((r) => r.id === rowId)!;
  return row.options!.reduce(
    (acc, option, i) => setRowOptionLabel(acc, rowId, option.id, i === 0 ? "Да" : "Нет"),
    question,
  );
}

test("тема без вопросов и тема без подписи названы причинами", () => {
  const named = (q: SurveyQuestion) => ({ ...q, label: "Вопрос" });
  let m = named(draft("matrix_single"));
  m = setRowLabel(m, m.rows![0].id, "Строка");
  m = fillRow(m, m.rows![0].id);

  assert.ok(
    draftIssues(m).some((r) => /подпис.*тем|тем.*подпис/i.test(r)),
    "тема без подписи должна называться причиной",
  );

  const withLabel = setThemeLabel(m, m.themes![0].id, "Патриотизм");
  assert.deepEqual(draftIssues(withLabel), []);

  /**
   * Новая тема заводится сразу с вопросом внутри, поэтому пустой она через
   * «добавить тему» не бывает. Но становится — если удалить её последний
   * вопрос. Это и есть путь, который надо удержать.
   */
  let second = addTheme(withLabel);
  second = setThemeLabel(second, second.themes![1].id, "Пустая");
  second = setRowLabel(second, second.rows!.at(-1)!.id, "Вопрос");
  second = fillRow(second, second.rows!.at(-1)!.id);
  assert.deepEqual(draftIssues(second), [], "тема с вопросом не должна ни на что жаловаться");

  const emptied = removeRow(second, second.rows!.at(-1)!.id);
  assert.ok(
    draftIssues(emptied).some((r) => /без вопросов|ни одного вопроса/i.test(r)),
    "тема, из которой удалили последний вопрос, должна называться причиной: " +
      "в отчёте она даст пустую группу",
  );
});

test("собранная деревом матрица принимается валидатором", async () => {
  const { validateSurvey } = await import("./server/survey-validator.ts");
  const { DEFAULT_QUESTIONS } = await import("./survey-composition.ts");

  let m: SurveyQuestion = { ...draft("matrix_single"), label: "Темы проекта" };
  m = setThemeLabel(m, m.themes![0].id, "Патриотизм");
  m = setRowLabel(m, m.rows![0].id, "Гордость за страну");
  const row = m.rows![0];
  m = setRowOptionLabel(m, row.id, row.options![0].id, "Поднималась");
  m = setRowOptionLabel(m, row.id, row.options![1].id, "Не поднималась");

  assert.deepEqual(draftIssues(m), []);

  const result = validateSurvey({ name: "Проверка", questions: [...DEFAULT_QUESTIONS, m] });
  assert.deepEqual(result.errors, [], "редактор собрал матрицу, которую сервер отвергнет");
});
