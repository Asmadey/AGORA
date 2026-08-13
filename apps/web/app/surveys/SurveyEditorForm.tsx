"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { SurveyBuilder, BASE_QUESTIONS } from "@/components/agora/SurveyBuilder";
import { ErrorState } from "@/components/agora/States";
import type { SurveyQuestion } from "@/lib/agora-types";

/**
 * Редактор анкеты: конструктор + сохранение.
 *
 * Клиентский он ровно настолько, насколько нужно: правка вопросов идёт в
 * состоянии, всё остальное отдано серверу. Сохранение уходит в
 * `PUT /api/surveys` — тот же маршрут, что и у визарда, с той же валидацией по
 * JSON Schema.
 *
 * ─── Ошибки валидации показываются целиком ─────────────────────────────────
 * Маршрут возвращает `details` — список конкретных претензий вида
 * «questions[5]: scaleMax должен быть больше scaleMin». Свести их к «не удалось
 * сохранить» значит заставить пользователя искать, что именно не так, в анкете
 * из пятнадцати вопросов. Прототип на этом месте показывал `alert()` с текстом
 * исключения.
 */
export function SurveyEditorForm({
  surveyId,
  initialName,
  initialQuestions,
}: {
  /** `undefined` — новая анкета: маршрут создаст её и вернёт id. */
  surveyId?: string;
  initialName: string;
  initialQuestions?: SurveyQuestion[];
}) {
  const router = useRouter();
  const [name, setName] = useState(initialName);
  const [questions, setQuestions] = useState<SurveyQuestion[]>(
    initialQuestions ?? BASE_QUESTIONS,
  );
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  async function save() {
    setSaving(true);
    setErrors([]);
    setSaved(false);
    try {
      const res = await fetch("/api/surveys", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: surveyId, name: name.trim(), questions }),
      });
      const payload = await res.json().catch(() => ({}));

      if (!res.ok) {
        setErrors(
          payload.details?.length
            ? payload.details
            : [payload.error ?? `Сервер ответил ${res.status}`],
        );
        return;
      }

      setSaved(true);
      if (!surveyId && payload.id) {
        // Новая анкета получила идентификатор — переходим на её адрес, иначе
        // второе нажатие «Сохранить» завело бы вторую анкету.
        router.replace(`/surveys/${payload.id}`);
      }
      router.refresh();
    } catch (error) {
      setErrors([`Запрос не дошёл: ${(error as Error).message}`]);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="max-w-xl space-y-2">
        <label htmlFor="survey-name" className="block text-sm font-medium">
          Название анкеты
        </label>
        <input
          id="survey-name"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setSaved(false);
          }}
          maxLength={200}
          className="w-full rounded-md border border-hairline bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-muted-foreground/60"
        />
      </div>

      <SurveyBuilder
        questions={questions}
        onChange={(qs) => {
          setQuestions(qs);
          setSaved(false);
        }}
      />

      {errors.length > 0 && (
        <ErrorState
          title="Анкета не сохранена"
          reason={errors.join("\n")}
        />
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving || !name.trim()}
          className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {saving ? "Сохранение…" : "Сохранить"}
        </button>
        {saved && <span className="text-sm text-success">Сохранено</span>}
      </div>
    </div>
  );
}
