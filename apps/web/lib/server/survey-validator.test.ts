import assert from "node:assert/strict";
import { test } from "node:test";

import { validateSurvey, getSurveySchema } from "./survey-validator.ts";

/**
 * Валидатор анкеты: что разрешено и что осталось запрещено.
 *
 * ─── Зачем файл ───────────────────────────────────────────────────────────
 * Валидатор — единственное место, решающее, попадёт ли анкета в базу, и до сих
 * пор он не был покрыт ни одним тестом. Правка здесь не ломает ни один экран:
 * конструктор продолжает рисоваться, кнопка продолжает нажиматься, а отказ
 * приходит уже из сети — то есть регрессию видно только тому, кто сохраняет
 * анкету руками.
 *
 * Тесты парные: на каждое послабление — проверка, что рядом ничего не
 * открылось. Снять требование пяти базовых критериев легко; вместе с ним
 * случайно снять «базовый обязан быть шкалой 1–10» — тоже легко, и вот это
 * уже сдвинуло бы средние, по которым идёт сравнение с корпусом.
 */

type Q = Record<string, unknown>;

const scale = (id: string, label: string, extra: Q = {}): Q => ({
  id,
  label,
  type: "scale",
  // Умолчание — шкала базовых критериев (0–10). Помощник чаще всего строит
  // именно их, а свою шкалу тест задаёт явно.
  scaleMin: 0,
  scaleMax: 10,
  ...extra,
});

const BASE: Q[] = [
  scale("b1", "Общее впечатление", { baseKey: "overall_impression" }),
  scale("b2", "Сюжет", { baseKey: "plot" }),
  scale("b3", "Игра актёров", { baseKey: "acting" }),
  scale("b4", "Музыка", { baseKey: "music" }),
  scale("b5", "Качество съёмок", { baseKey: "cinematography" }),
];

const survey = (questions: Q[], name = "Анкета") => ({ name, questions });

test("базовые критерии необязательны", async (t) => {
  await t.test("полная анкета из пяти базовых принимается", () => {
    const r = validateSurvey(survey(BASE));
    assert.equal(r.valid, true, r.errors.join("; "));
  });

  await t.test("часть базовых снята — принимается", () => {
    // Сценарий владельца: убрать «Музыку» и «Качество съёмок».
    const r = validateSurvey(survey(BASE.slice(0, 3)));
    assert.equal(r.valid, true, r.errors.join("; "));
  });

  await t.test("все базовые сняты, остались только свои — принимается", () => {
    const r = validateSurvey(
      survey([
        scale("c1", "Насколько понятен конфликт героя"),
        { id: "c2", label: "Что запомнилось", type: "open", scaleMin: 1, scaleMax: 10 },
      ]),
    );
    assert.equal(r.valid, true, r.errors.join("; "));
  });

  await t.test("один-единственный вопрос — принимается", () => {
    const r = validateSurvey(survey([scale("c1", "Досмотрели бы?")]));
    assert.equal(r.valid, true, r.errors.join("; "));
  });

  await t.test("ноль вопросов — отказ", () => {
    // Не послабление: анкета без вопросов означает оплаченный прогон, в котором
    // персону не о чем спрашивать.
    const r = validateSurvey(survey([]));
    assert.equal(r.valid, false);
    assert.match(r.errors.join("; "), /хотя бы один вопрос/);
  });
});

test("то, что осталось строгим", async (t) => {
  await t.test("базовый критерий не может быть не-шкалой", () => {
    // Иначе ключ overall_impression с типом open попал бы в средние, по которым
    // считается сравнение с корпусом.
    const r = validateSurvey(
      survey([{ id: "b1", label: "Общее", type: "open", scaleMin: 1, scaleMax: 10, baseKey: "overall_impression" }]),
    );
    assert.equal(r.valid, false);
    assert.match(r.errors.join("; "), /должен быть type=scale/);
  });

  await t.test("базовый критерий на чужой шкале отвергается", () => {
    // Здесь стояло «критерии не могут быть на РАЗНЫХ шкалах». Правило прожило
    // несколько часов: одинаковая, но чужая шкала проходила его насквозь, а
    // пороги расчёта абсолютны. Теперь шкала у базового критерия ровно одна.
    const r = validateSurvey(
      survey([
        scale("b1", "Общее", { baseKey: "overall_impression", scaleMin: 0, scaleMax: 10 }),
        scale("b2", "Сюжет", { baseKey: "plot", scaleMin: 1, scaleMax: 5 }),
      ]),
    );
    assert.equal(r.valid, false);
    assert.match(r.errors.join("; "), /0–10/);
  });

  await t.test("одна шкала 0–10 у всех критериев принимается", () => {
    // Анкета заказчика. Прежняя проверка отвергала её целиком.
    const r = validateSurvey(
      survey([
        scale("b1", "Общее", { baseKey: "overall_impression", scaleMin: 0, scaleMax: 10 }),
        scale("b2", "Сюжет", { baseKey: "plot", scaleMin: 0, scaleMax: 10 }),
      ]),
    );
    assert.equal(r.valid, true, r.errors.join("; "));
  });

  await t.test("baseKey не повторяется", () => {
    const r = validateSurvey(
      survey([
        scale("b1", "Общее", { baseKey: "overall_impression" }),
        scale("b2", "Общее ещё раз", { baseKey: "overall_impression" }),
      ]),
    );
    assert.equal(r.valid, false);
    assert.match(r.errors.join("; "), /дубликат/);
  });

  await t.test("неизвестный baseKey отвергается", () => {
    const r = validateSurvey(survey([scale("b1", "Свет", { baseKey: "lighting" })]));
    assert.equal(r.valid, false);
    assert.match(r.errors.join("; "), /baseKey/);
  });

  await t.test("неизвестный тип вопроса отвергается", () => {
    const r = validateSurvey(
      survey([{ id: "c1", label: "Что-то", type: "matrix", scaleMin: 1, scaleMax: 10 }]),
    );
    assert.equal(r.valid, false);
    assert.match(r.errors.join("; "), /type/);
  });

  await t.test("пустое название отвергается", () => {
    const r = validateSurvey(survey([scale("c1", "Вопрос")], "   "));
    assert.equal(r.valid, false);
    assert.match(r.errors.join("; "), /name/);
  });
});

test("схема в packages/shared согласна с валидатором", () => {
  // Два описания одного контракта на двух языках расходятся молча: валидатор
  // примет анкету, которую схема считает невалидной, и наоборот. Схему читает
  // воркер и CDD-тесты, валидатор — маршрут записи.
  const schema = getSurveySchema() as {
    properties: { questions: { minItems: number } };
  };
  assert.equal(
    schema.properties.questions.minItems,
    1,
    "survey.schema.json всё ещё требует пять вопросов, а валидатор — один",
  );
});

test("базовый критерий живёт только на шкале 0–10", async (t) => {
  /**
   * Решение владельца 17.09.2026.
   *
   * ─── Почему снова жёсткая привязка, и почему к другим числам ─────────────
   * Привязку к 1–10 сняли в тот же день: анкета заказчика пришла на 0–10 и
   * отвергалась целиком. Вместо неё поставили согласие критериев между собой —
   * «любая шкала, лишь бы одна». Этого оказалось мало.
   *
   * Расчёты Приложения 2 читают баллы абсолютными порогами: доля 8–10,
   * промоутеры 9–10, детракторы 0–6. Пороги — определение заказчика, и они
   * осмысленны ровно на 0–10. Анкета на 1–5 проходила бы валидатор, а
   * интегральный индекс удовлетворённости выходил бы 0.0 и NPS −1.0 — молча,
   * числами правильного вида.
   *
   * Отсюда: ключ базового критерия — контракт с расчётом, а не просто имя
   * колонки. Хочешь свою шкалу — заводи вопрос без `baseKey`, и он не попадёт
   * ни в индекс, ни в сравнение с корпусом.
   */
  await t.test("0–10 принимается", () => {
    const r = validateSurvey(
      survey([scale("b1", "Общее", { baseKey: "overall_impression", scaleMin: 0, scaleMax: 10 })]),
    );
    assert.equal(r.valid, true, r.errors.join("; "));
  });

  await t.test("1–10 отвергается", () => {
    const r = validateSurvey(
      survey([scale("b1", "Общее", { baseKey: "overall_impression", scaleMin: 1, scaleMax: 10 })]),
    );
    assert.equal(r.valid, false, "прежняя шкала заказчика больше не принимается");
    assert.match(r.errors.join("; "), /0–10/);
  });

  await t.test("1–5 отвергается до того, как индекс выйдет нулём", () => {
    const r = validateSurvey(
      survey([scale("b1", "Общее", { baseKey: "overall_impression", scaleMin: 1, scaleMax: 5 })]),
    );
    assert.equal(r.valid, false);
  });

  await t.test("вопрос без baseKey свою шкалу сохраняет", () => {
    const r = validateSurvey(
      survey([scale("c1", "Своё", { scaleMin: 1, scaleMax: 5 })]),
    );
    assert.equal(r.valid, true, r.errors.join("; "));
  });
});
