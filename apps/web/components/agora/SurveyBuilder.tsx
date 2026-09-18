"use client";

import { useState } from "react";
import { Check, Pencil, Trash2, Plus, Info, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Chip } from "@/components/agora/Primitives";
import type { SurveyQuestion, QuestionType } from "@/lib/agora-types";
import {
  BASE_QUESTIONS,
  BASE_SCALE_LABEL,
  groundingIssues,
  isMandatory,
  newQuestionDraft,
} from "@/lib/survey-composition";

/**
 * Конструктор анкеты (задача #10).
 *
 * Пять базовых критериев редактируемы наравне с пользовательскими вопросами, но
 * их правка помечается: средние по корпусу из 165 респондентов посчитаны именно
 * по паре «ключ + шкала», и при смене типа или удалении критерия сравнивать
 * результат прогона становится не с чем. Метрика persona_grounding в этом случае
 * теряет опору, поэтому последствие показано на экране, а не спрятано в
 * документации. Кнопка возврата к исходному состоянию есть у каждого изменённого
 * базового критерия — цена ошибки должна быть один клик.
 */

/**
 * Пять типов вместо прежних шести.
 *
 * «Эмоции», «удержание», «рекомендация» и «доля просмотра» были не типами, а
 * ПРЕСЕТАМИ: эмоции — выбор нескольких из готового словаря, удержание — выбор
 * одного из трёх, рекомендация и доля — шкалы. Каждый нёс свою ветку в
 * конструкторе, промпте, правилах QA, агрегате, графиках и выгрузке; свёрнутые,
 * они дают один редьюсер и один график на тип. Пресет живёт в данных анкеты —
 * готовым списком `options`, — а не в перечне типов.
 *
 * `chartable` отвечает на вопрос, который пользователь задаёт при создании
 * вопроса: построится ли по нему график. У открытого ответа не построится
 * никогда — его нельзя упорядочить и нечего считать, — и сказать об этом надо
 * ДО прогона, а не после.
 */
export const QUESTION_TYPES: {
  v: QuestionType;
  label: string;
  hint: string;
  chartable: boolean;
}[] = [
  { v: "scale", label: "Шкала", hint: "числовая оценка в заданных границах", chartable: true },
  { v: "single_choice", label: "Один из списка", hint: "ровно один вариант из закрытого перечня", chartable: true },
  { v: "multi_choice", label: "Несколько из списка", hint: "до N вариантов из закрытого перечня", chartable: true },
  { v: "matrix_single", label: "Матрица", hint: "по одному варианту на каждую строку", chartable: true },
  { v: "open", label: "Открытый", hint: "свободный ответ текстом — график не построится", chartable: false },
];

const TYPE_LABEL: Record<QuestionType, string> = Object.fromEntries(
  QUESTION_TYPES.map((t) => [t.v, t.label]),
) as Record<QuestionType, string>;

/** Базовый критерий считается изменённым, если разошлись подпись, тип или шкала. */
function isModified(q: SurveyQuestion): boolean {
  const original = BASE_QUESTIONS.find((b) => b.baseKey === q.baseKey);
  if (!original) return false;
  return (
    original.label !== q.label ||
    original.type !== q.type ||
    original.scaleMin !== q.scaleMin ||
    original.scaleMax !== q.scaleMax
  );
}

function describe(q: SurveyQuestion): string {
  return q.type === "scale" ? `${q.scaleMin}–${q.scaleMax}` : TYPE_LABEL[q.type];
}

// ─── Форма правки одного вопроса ──────────────────────────────────────────

function QuestionEditor({
  draft,
  onChange,
  onSave,
  onCancel,
}: {
  draft: SurveyQuestion;
  onChange: (q: SurveyQuestion) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const invalidLabel = draft.label.trim().length === 0;
  // Границы есть только у шкалы; у выбора из списка их нет и быть не может.
  const invalidScale =
    draft.type === "scale" &&
    (draft.scaleMin === undefined ||
      draft.scaleMax === undefined ||
      draft.scaleMin >= draft.scaleMax);

  return (
    <div className="space-y-3 rounded-md border border-ink/40 bg-secondary/40 p-4">
      <div>
        <label className="text-xs text-slate" htmlFor={`label-${draft.id}`}>
          Формулировка вопроса
        </label>
        <input
          id={`label-${draft.id}`}
          autoFocus
          value={draft.label}
          onChange={(e) => onChange({ ...draft, label: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !invalidLabel && !invalidScale) onSave();
            if (e.key === "Escape") onCancel();
          }}
          placeholder="Например: насколько убедителен финал?"
          className="mt-1.5 w-full rounded-md border border-hairline bg-background px-3 py-2 text-sm outline-none focus:border-ink/60"
        />
      </div>

      <div>
        <span className="text-xs text-slate">Тип ответа</span>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {QUESTION_TYPES.map((t) => (
            <button
              key={t.v}
              type="button"
              title={t.hint}
              onClick={() => onChange({ ...draft, type: t.v })}
              className={cn(
                "rounded-full border px-3 py-1 text-xs transition-colors",
                draft.type === t.v
                  ? "border-ink bg-secondary text-foreground"
                  : "border-hairline text-slate hover:bg-secondary",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-slate">
          {QUESTION_TYPES.find((t) => t.v === draft.type)?.hint}
        </p>
      </div>

      {draft.type === "scale" && (
        <div className="flex items-end gap-3">
          <div>
            <label className="text-xs text-slate" htmlFor={`min-${draft.id}`}>
              От
            </label>
            <input
              id={`min-${draft.id}`}
              type="number"
              value={draft.scaleMin}
              onChange={(e) => onChange({ ...draft, scaleMin: Number(e.target.value) })}
              className="mt-1.5 w-20 rounded-md border border-hairline bg-background px-3 py-2 text-sm tabular-nums outline-none focus:border-ink/60"
            />
          </div>
          <div>
            <label className="text-xs text-slate" htmlFor={`max-${draft.id}`}>
              До
            </label>
            <input
              id={`max-${draft.id}`}
              type="number"
              value={draft.scaleMax}
              onChange={(e) => onChange({ ...draft, scaleMax: Number(e.target.value) })}
              className="mt-1.5 w-20 rounded-md border border-hairline bg-background px-3 py-2 text-sm tabular-nums outline-none focus:border-ink/60"
            />
          </div>
          {invalidScale && (
            <p className="pb-2 text-xs text-danger">Нижняя граница должна быть меньше верхней.</p>
          )}
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={onSave}
          disabled={invalidLabel || invalidScale}
          className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40"
        >
          Готово
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
        >
          Отмена
        </button>
      </div>
    </div>
  );
}

// ─── Строка обязательного вопроса ─────────────────────────────────────────

/**
 * Обязательный вопрос заказчика: только чтение.
 *
 * Ни правки, ни удаления — решение владельца от 17.09.2026. Кнопок здесь нет
 * не потому, что их «не успели добавить»: пятнадцать вопросов пронумерованы
 * заказчиком, отчёт и выгрузка ссылаются на эти номера, и снятый вопрос сделал
 * бы отчёт неполным незаметно для читателя.
 *
 * Формулировки заказчика длинные — по две-три строки. Обрезать их в одну, как
 * у своих вопросов, нельзя: оператор должен видеть, что именно спросят, чтобы
 * решить, нужны ли ему дополнительные вопросы.
 */
function MandatoryRow({ q }: { q: SurveyQuestion }) {
  const rows = q.rows?.length ?? 0;
  const options = q.options?.length ?? 0;

  return (
    <div className="flex items-start gap-3 rounded-md border border-hairline bg-secondary/20 px-4 py-2.5">
      <span className="w-6 shrink-0 pt-0.5 text-right text-xs tabular-nums text-stone">
        {q.number}
      </span>

      <div className="min-w-0 flex-1">
        <p className="text-sm leading-snug">{q.label}</p>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate">
          <span>{describe(q)}</span>
          {rows > 0 && <span>{rows} строк</span>}
          {options > 0 && <span>{options} вариантов</span>}
          {q.maxChoices && <span>до {q.maxChoices} ответов</span>}
          {q.baseKey && <span className="font-mono">{q.baseKey}</span>}
        </p>
      </div>
    </div>
  );
}

// ─── Строка вопроса ───────────────────────────────────────────────────────

function QuestionRow({
  q,
  index,
  onEdit,
  onDelete,
  onRestore,
}: {
  q: SurveyQuestion;
  /** Сквозной номер по всей анкете. */
  index: number;
  onEdit: () => void;
  onDelete: () => void;
  onRestore: () => void;
}) {
  const modified = isModified(q);

  return (
    <div className="flex items-center gap-3 rounded-md border border-hairline px-4 py-2.5">
      {/* Номер, а не маркер списка: по нему видно, сколько вопросов задаётся
          персоне, и на него ссылаются, обсуждая анкету. Галочка базового
          критерия переехала правее — она про происхождение вопроса, а не про
          его место. */}
      <span className="w-6 shrink-0 text-right text-xs tabular-nums text-stone">{index}</span>

      {q.baseKey ? (
        <Check className={cn("h-4 w-4 shrink-0", modified ? "text-warning" : "text-success")} />
      ) : (
        <span className="h-4 w-4 shrink-0" />
      )}

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">{q.label}</p>
        {q.baseKey && (
          <p className="mt-0.5 truncate font-mono text-[11px] text-slate">{q.baseKey}</p>
        )}
      </div>

      <span className="shrink-0 text-xs text-slate">{describe(q)}</span>

      {modified && (
        <button
          type="button"
          onClick={onRestore}
          title="Вернуть исходную формулировку и шкалу"
          aria-label={`Вернуть исходный критерий: ${q.label}`}
          className="shrink-0 rounded p-1.5 text-slate transition-colors hover:bg-secondary hover:text-foreground"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      )}
      <button
        type="button"
        onClick={onEdit}
        title="Редактировать"
        aria-label={`Редактировать вопрос: ${q.label}`}
        className="shrink-0 rounded p-1.5 text-slate transition-colors hover:bg-secondary hover:text-foreground"
      >
        <Pencil className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={onDelete}
        title="Удалить"
        aria-label={`Удалить вопрос: ${q.label}`}
        className="shrink-0 rounded p-1.5 text-slate transition-colors hover:bg-danger-soft hover:text-danger"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}

// ─── Конструктор ──────────────────────────────────────────────────────────

export function SurveyBuilder({
  questions,
  onChange,
}: {
  questions: SurveyQuestion[];
  onChange: (qs: SurveyQuestion[]) => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<SurveyQuestion | null>(null);

  /**
   * Три группы, а не две.
   *
   * Обязательный блок заказчика несёт свои пять базовых критериев (его вопросы
   * 1–5). Если делить только на «базовые» и «остальные», эти пять попадут в
   * первую группу и покажутся дважды: один раз как обязательные, второй — как
   * базовые. Поэтому обязательные отбираются первыми и из остальных групп
   * вычитаются.
   */
  const mandatory = questions.filter(isMandatory);
  const rest = questions.filter((q) => !isMandatory(q));
  const base = rest.filter((q) => q.baseKey);
  const custom = rest.filter((q) => !q.baseKey);

  const grounding = groundingIssues(questions);
  const groundingBroken = grounding.length > 0;

  const startEdit = (q: SurveyQuestion) => {
    setDraft({ ...q });
    setEditingId(q.id);
  };

  const startAdd = () => {
    const draft = newQuestionDraft(`q-${Date.now()}`);
    setDraft(draft);
    setEditingId(draft.id);
  };

  const commit = () => {
    if (!draft) return;
    const exists = questions.some((q) => q.id === draft.id);
    onChange(
      exists ? questions.map((q) => (q.id === draft.id ? draft : q)) : [...questions, draft],
    );
    setDraft(null);
    setEditingId(null);
  };

  const cancel = () => {
    setDraft(null);
    setEditingId(null);
  };

  const remove = (id: string) => {
    onChange(questions.filter((q) => q.id !== id));
    if (editingId === id) cancel();
  };

  const restore = (q: SurveyQuestion) => {
    const original = BASE_QUESTIONS.find((b) => b.baseKey === q.baseKey);
    if (!original) return;
    onChange(questions.map((x) => (x.id === q.id ? { ...original, id: x.id } : x)));
  };

  const restoreAllBase = () => {
    const kept = questions.filter((q) => !q.baseKey);
    onChange([...BASE_QUESTIONS, ...kept]);
    cancel();
  };

  /**
   * Номер вопроса — сквозной по всей анкете, а не внутри группы.
   *
   * Пользователь считает вопросы, а не разделы: «сколько всего спросят» —
   * это длина списка, который увидит персона. Нумерация внутри групп дала бы
   * две единицы и две двойки в одной анкете.
   */
  const numberOf = (q: SurveyQuestion) => questions.findIndex((x) => x.id === q.id) + 1;

  const renderList = (list: SurveyQuestion[]) =>
    list.map((q) =>
      editingId === q.id && draft ? (
        <QuestionEditor
          key={q.id}
          draft={draft}
          onChange={setDraft}
          onSave={commit}
          onCancel={cancel}
        />
      ) : (
        <QuestionRow
          key={q.id}
          q={q}
          index={numberOf(q)}
          onEdit={() => startEdit(q)}
          onDelete={() => remove(q.id)}
          onRestore={() => restore(q)}
        />
      ),
    );

  const addingNew = draft !== null && !questions.some((q) => q.id === draft.id);

  return (
    <div className="space-y-6">
      {mandatory.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between gap-4">
            <h2 className="text-sm font-semibold">Обязательные вопросы заказчика</h2>
            <span className="text-xs tabular-nums text-slate">{mandatory.length}</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-slate">
            Эти вопросы задаются в каждом исследовании и не редактируются: отчёт и
            выгрузка называют их номерами заказчика, и снятый вопрос сделал бы отчёт
            неполным незаметно для читателя. Гибкость — в дополнительных вопросах ниже.
          </p>

          <div className="mt-3 space-y-2">
            {mandatory.map((q) => (
              <MandatoryRow key={q.id} q={q} />
            ))}
          </div>
        </div>
      )}

      {(base.length > 0 || groundingBroken) && (
      <div>
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-sm font-semibold">Базовые критерии</h2>
          {groundingBroken && (
            <button
              type="button"
              onClick={restoreAllBase}
              className="text-xs text-slate underline-offset-2 transition-colors hover:text-foreground hover:underline"
            >
              Вернуть все пять как было
            </button>
          )}
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate">
          По этим пяти критериям посчитаны средние в корпусе 165 респондентов. Пока их
          тип и шкала {BASE_SCALE_LABEL} не тронуты, отчёт можно сравнивать с реальными
          данными.
        </p>

        <div className="mt-3 space-y-2">{renderList(base)}</div>

        {groundingBroken && (
          <p className="mt-3 flex gap-2 rounded-md border border-warning/30 bg-warning-soft/60 p-3 text-xs leading-relaxed text-warning">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              {grounding.join("; ")}. Сравнение с корпусом для затронутых критериев
              отключено — калибровка средних привязана к шкале {BASE_SCALE_LABEL}, и на
              другой шкале сопоставлять нечего. Проверка заземления (persona_grounding)
              по ним не считается. Прогон при этом выполнится: изменение легально, просто
              его цена — потеря опоры на реальные данные.
            </span>
          </p>
        )}
      </div>
      )}

      <div>
        <h2 className="text-sm font-semibold">Дополнительные вопросы</h2>
        <p className="mt-1 text-xs leading-relaxed text-slate">
          Задаются всем персонам после базовых. Заземления на корпус у них нет — сравнивать
          можно только прогоны между собой.
        </p>

        <div className="mt-3 space-y-2">
          {custom.length === 0 && !addingNew && (
            <p className="rounded-md border border-dashed border-hairline px-4 py-3 text-xs text-slate">
              Пока ни одного. Обязательных вопросов заказчика достаточно для полного отчёта.
            </p>
          )}
          {renderList(custom)}
          {addingNew && draft && (
            <QuestionEditor draft={draft} onChange={setDraft} onSave={commit} onCancel={cancel} />
          )}
        </div>

        {!addingNew && (
          <button
            type="button"
            onClick={startAdd}
            className="mt-2 flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-hairline py-3 text-sm text-slate transition-colors hover:border-muted-foreground/50 hover:text-foreground"
          >
            <Plus className="h-4 w-4" />
            Добавить вопрос
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-hairline pt-4">
        <Chip tone="outline">Всего вопросов: {questions.length}</Chip>
        {/* Предупреждение осталось, подтверждение снято: «заземление активно» —
            это состояние по умолчанию, и сообщать о нём значит приучать не
            читать эту строку. Красный флаг, который горит всегда, перестаёт
            быть флагом. */}
        {groundingBroken && (
          <Chip tone="outline">
            <span className="text-warning">заземление частично отключено</span>
          </Chip>
        )}
      </div>
    </div>
  );
}
