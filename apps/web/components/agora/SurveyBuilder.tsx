"use client";

import { useState } from "react";
import { Check, Pencil, Trash2, Plus, Info, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Chip } from "@/components/agora/Primitives";
import type { SurveyQuestion, QuestionType } from "@/lib/agora-types";

/**
 * Конструктор анкеты (задача #10).
 *
 * Пять базовых критериев редактируемы наравне с пользовательскими вопросами, но
 * их правка помечается: средние по корпусу из 165 респондентов посчитаны именно
 * по паре «ключ + шкала 1–10», и при смене типа или удалении критерия сравнивать
 * результат прогона становится не с чем. Метрика persona_grounding в этом случае
 * теряет опору, поэтому последствие показано на экране, а не спрятано в
 * документации. Кнопка возврата к исходному состоянию есть у каждого изменённого
 * базового критерия — цена ошибки должна быть один клик.
 */

export const QUESTION_TYPES: { v: QuestionType; label: string; hint: string }[] = [
  { v: "scale", label: "Шкала", hint: "числовая оценка в заданных границах" },
  { v: "emotions", label: "Эмоции", hint: "набор эмоций, вызванных материалом" },
  { v: "retention", label: "Удержание", hint: "момент, где persona перестала бы смотреть" },
  { v: "recommendation", label: "Рекомендация", hint: "порекомендует ли и кому" },
  { v: "open", label: "Открытый", hint: "свободный ответ текстом" },
];

const TYPE_LABEL: Record<QuestionType, string> = Object.fromEntries(
  QUESTION_TYPES.map((t) => [t.v, t.label]),
) as Record<QuestionType, string>;

/** Исходные пять критериев. Ключи зафиксированы acceptance-критерием задачи #10. */
export const BASE_QUESTIONS: SurveyQuestion[] = [
  { id: "base-1", baseKey: "overall_impression", label: "Общее впечатление", type: "scale", scaleMin: 1, scaleMax: 10 },
  { id: "base-2", baseKey: "plot", label: "Сюжет", type: "scale", scaleMin: 1, scaleMax: 10 },
  { id: "base-3", baseKey: "acting", label: "Актёрская игра", type: "scale", scaleMin: 1, scaleMax: 10 },
  { id: "base-4", baseKey: "music", label: "Музыка", type: "scale", scaleMin: 1, scaleMax: 10 },
  { id: "base-5", baseKey: "cinematography", label: "Операторская работа", type: "scale", scaleMin: 1, scaleMax: 10 },
];

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
  const invalidScale = draft.type === "scale" && draft.scaleMin >= draft.scaleMax;

  return (
    <div className="space-y-3 rounded-md border border-foreground/40 bg-secondary/40 p-4">
      <div>
        <label className="text-xs text-muted-foreground" htmlFor={`label-${draft.id}`}>
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
          className="mt-1.5 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-foreground/60"
        />
      </div>

      <div>
        <span className="text-xs text-muted-foreground">Тип ответа</span>
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
                  ? "border-foreground bg-secondary text-foreground"
                  : "border-border text-muted-foreground hover:bg-secondary/50",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">
          {QUESTION_TYPES.find((t) => t.v === draft.type)?.hint}
        </p>
      </div>

      {draft.type === "scale" && (
        <div className="flex items-end gap-3">
          <div>
            <label className="text-xs text-muted-foreground" htmlFor={`min-${draft.id}`}>
              От
            </label>
            <input
              id={`min-${draft.id}`}
              type="number"
              value={draft.scaleMin}
              onChange={(e) => onChange({ ...draft, scaleMin: Number(e.target.value) })}
              className="mt-1.5 w-20 rounded-md border border-border bg-background px-3 py-2 text-sm tabular-nums outline-none focus:border-foreground/60"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground" htmlFor={`max-${draft.id}`}>
              До
            </label>
            <input
              id={`max-${draft.id}`}
              type="number"
              value={draft.scaleMax}
              onChange={(e) => onChange({ ...draft, scaleMax: Number(e.target.value) })}
              className="mt-1.5 w-20 rounded-md border border-border bg-background px-3 py-2 text-sm tabular-nums outline-none focus:border-foreground/60"
            />
          </div>
          {invalidScale && (
            <p className="pb-2 text-xs text-rose-300">Нижняя граница должна быть меньше верхней.</p>
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
          className="rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
        >
          Отмена
        </button>
      </div>
    </div>
  );
}

// ─── Строка вопроса ───────────────────────────────────────────────────────

function QuestionRow({
  q,
  onEdit,
  onDelete,
  onRestore,
}: {
  q: SurveyQuestion;
  onEdit: () => void;
  onDelete: () => void;
  onRestore: () => void;
}) {
  const modified = isModified(q);

  return (
    <div className="flex items-center gap-3 rounded-md border border-border px-4 py-2.5">
      {q.baseKey ? (
        <Check className={cn("h-4 w-4 shrink-0", modified ? "text-amber-400" : "text-emerald-400")} />
      ) : (
        <span className="h-4 w-4 shrink-0" />
      )}

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">{q.label}</p>
        {q.baseKey && (
          <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{q.baseKey}</p>
        )}
      </div>

      <span className="shrink-0 text-xs text-muted-foreground">{describe(q)}</span>

      {modified && (
        <button
          type="button"
          onClick={onRestore}
          title="Вернуть исходную формулировку и шкалу"
          aria-label={`Вернуть исходный критерий: ${q.label}`}
          className="shrink-0 rounded p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      )}
      <button
        type="button"
        onClick={onEdit}
        title="Редактировать"
        aria-label={`Редактировать вопрос: ${q.label}`}
        className="shrink-0 rounded p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <Pencil className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={onDelete}
        title="Удалить"
        aria-label={`Удалить вопрос: ${q.label}`}
        className="shrink-0 rounded p-1.5 text-muted-foreground transition-colors hover:bg-rose-500/10 hover:text-rose-300"
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

  const base = questions.filter((q) => q.baseKey);
  const custom = questions.filter((q) => !q.baseKey);

  const missingBase = BASE_QUESTIONS.filter(
    (b) => !questions.some((q) => q.baseKey === b.baseKey),
  );
  const groundingBroken =
    missingBase.length > 0 ||
    base.some((q) => q.type !== "scale" || q.scaleMin !== 1 || q.scaleMax !== 10);

  const startEdit = (q: SurveyQuestion) => {
    setDraft({ ...q });
    setEditingId(q.id);
  };

  const startAdd = () => {
    const q: SurveyQuestion = {
      id: `q-${Date.now()}`,
      label: "",
      type: "scale",
      scaleMin: 1,
      scaleMax: 10,
    };
    setDraft(q);
    setEditingId(q.id);
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
          onEdit={() => startEdit(q)}
          onDelete={() => remove(q.id)}
          onRestore={() => restore(q)}
        />
      ),
    );

  const addingNew = draft !== null && !questions.some((q) => q.id === draft.id);

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-sm font-semibold">Базовые критерии</h2>
          {groundingBroken && (
            <button
              type="button"
              onClick={restoreAllBase}
              className="text-xs text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline"
            >
              Вернуть все пять как было
            </button>
          )}
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          По этим пяти критериям посчитаны средние в корпусе 165 респондентов. Пока их
          подписи и шкала 1–10 не тронуты, отчёт можно сравнивать с реальными данными.
        </p>

        <div className="mt-3 space-y-2">{renderList(base)}</div>

        {groundingBroken && (
          <p className="mt-3 flex gap-2 rounded-md border border-amber-500/25 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-200/80">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              {missingBase.length > 0
                ? `Удалено базовых критериев: ${missingBase.length}. `
                : "Тип или шкала базового критерия изменены. "}
              Сравнение с корпусом для затронутых критериев отключено — калибровка средних
              привязана к шкале 1–10, и на другой шкале сопоставлять нечего. Проверка
              заземления (persona_grounding) по ним не считается. Прогон при этом
              выполнится: изменение легально, просто его цена — потеря опоры на реальные
              данные.
            </span>
          </p>
        )}
      </div>

      <div>
        <h2 className="text-sm font-semibold">Дополнительные вопросы</h2>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Задаются всем персонам после базовых. Заземления на корпус у них нет — сравнивать
          можно только прогоны между собой.
        </p>

        <div className="mt-3 space-y-2">
          {custom.length === 0 && !addingNew && (
            <p className="rounded-md border border-dashed border-border px-4 py-3 text-xs text-muted-foreground">
              Пока ни одного. Анкета из пяти базовых критериев полностью рабочая.
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
            className="mt-2 flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-border py-3 text-sm text-muted-foreground transition-colors hover:border-muted-foreground/50 hover:text-foreground"
          >
            <Plus className="h-4 w-4" />
            Добавить вопрос
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
        <Chip tone="outline">Всего вопросов: {questions.length}</Chip>
        {groundingBroken ? (
          <Chip tone="outline">
            <span className="text-amber-300">заземление частично отключено</span>
          </Chip>
        ) : (
          <Chip tone="outline">заземление на корпус активно</Chip>
        )}
      </div>
    </div>
  );
}
