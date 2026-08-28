"use client";

import { useEffect, useState } from "react";
import { Loader2, ExternalLink } from "lucide-react";
import Link from "next/link";

import { SurveyBuilder, BASE_QUESTIONS } from "@/components/agora/SurveyBuilder";
import {
  DRAFT_SURVEY_ID,
  questionsDiffer,
  questionsOf,
  type SurveyOption,
} from "@/lib/survey-sync";
import type { SurveyQuestion } from "@/lib/agora-types";

/**
 * Шаг «Опрос»: выбор анкеты и правка её вопросов.
 *
 * ─── Что здесь появилось и почему это починка, а не функция ───────────────
 * Раздел «Анкеты» и шаг «Опрос» до этой правки не знали друг о друге. В базе
 * лежала таблица `surveys`, в задаче — колонка `survey_id`, маршрут запуска
 * умел читать вопросы по `surveyId` — а визард не отправлял его вовсе и
 * показывал захардкоженные пять базовых критериев. Воркер получал
 * `survey: null` и законно шёл по тем же пяти. Поэтому прогон с анкетой из
 * девяти вопросов и прогон без анкеты давали одинаковый результат, и отличить
 * их было нечем.
 *
 * ─── Почему правка сохраняется кнопкой, а не сама ─────────────────────────
 * Анкета — общий объект арендатора: на неё ссылаются прошлые прогоны и её
 * увидит следующий, кто откроет визард. Автосохранение означало бы, что
 * случайно удалённый здесь вопрос молча исчезает у всех. Кнопка называет цену
 * до нажатия.
 *
 * Отчёты прошлых прогонов правка не двигает: они читают `survey_asked` —
 * снимок вопросов на момент прогона, а не анкету на момент чтения.
 */

export function SurveyPicker({
  surveyId,
  onSurveyIdChange,
  questions,
  onChange,
}: {
  surveyId: string | null;
  onSurveyIdChange: (id: string) => void;
  questions: SurveyQuestion[];
  onChange: (qs: SurveyQuestion[]) => void;
}) {
  const [surveys, setSurveys] = useState<SurveyOption[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/surveys");
        if (!res.ok) throw new Error(`сервер ответил ${res.status}`);
        const data = (await res.json()) as { surveys?: SurveyOption[] };
        if (cancelled) return;
        const list = Array.isArray(data.surveys) ? data.surveys : [];
        setSurveys(list);
        // Выбор по умолчанию делается здесь, а не в визарде: только здесь
        // известно, есть ли у арендатора хоть одна анкета. Без этого первый
        // прогон нового арендатора ушёл бы вообще без `surveyId` — то есть
        // ровно с тем дефектом, ради которого компонент и заведён.
        if (!surveyId) {
          const first = list[0];
          onSurveyIdChange(first ? first.id : DRAFT_SURVEY_ID);
          if (first) onChange(questionsOf(list, first.id, BASE_QUESTIONS));
        }
      } catch (e) {
        if (!cancelled) setLoadError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Список читается один раз при входе на шаг: анкеты не меняются, пока
    // пользователь стоит на этом экране, а перечитывание сбрасывало бы правки.
  }, []);

  const selected = surveys?.find((s) => s.id === surveyId) ?? null;
  const dirty = selected ? questionsDiffer(selected.questions, questions) : false;

  const pick = (id: string) => {
    onSurveyIdChange(id);
    onChange(questionsOf(surveys ?? [], id, BASE_QUESTIONS));
    setSaveError(null);
    setSavedAt(null);
  };

  async function save() {
    if (!selected) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await fetch("/api/surveys", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: selected.id, name: selected.name, questions }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        // `details` — перечень конкретных претензий валидатора. Без него на
        // экран попадает «некорректные параметры», и непонятно, какой вопрос
        // чинить.
        const details: string[] = Array.isArray(payload?.details) ? payload.details : [];
        throw new Error(details.length ? details.join("; ") : (payload?.error ?? `сервер ответил ${res.status}`));
      }
      // Список обновляется на месте: иначе кнопка «Сохранить» осталась бы
      // активной после успешного сохранения — сравнение шло бы со старым
      // содержимым.
      setSurveys((prev) =>
        (prev ?? []).map((s) =>
          s.id === selected.id ? { ...s, questions: questions.map((q) => ({ ...q })) } : s,
        ),
      );
      setSavedAt(Date.now());
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const SELECT_CLASS =
    "rounded-md border border-hairline bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-muted-foreground/60";

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-hairline bg-card p-5">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-slate">Анкета</span>
            <select
              value={surveyId ?? ""}
              onChange={(e) => pick(e.target.value)}
              disabled={surveys === null}
              className={SELECT_CLASS}
            >
              {surveys === null && <option value="">Загрузка…</option>}
              {surveys?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.questions.length}{" "}
                  {s.questions.length === 1 ? "вопрос" : s.questions.length < 5 ? "вопроса" : "вопросов"}
                </option>
              ))}
              {/* Черновик предлагается, только когда сохранённых анкет нет:
                  рядом с настоящими он был бы способом случайно завести
                  двадцать безымянных копий. */}
              {surveys?.length === 0 && (
                <option value={DRAFT_SURVEY_ID}>Базовая анкета (будет создана)</option>
              )}
            </select>
          </label>

          {selected && (
            <button
              type="button"
              onClick={() => void save()}
              disabled={!dirty || saving}
              className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary disabled:opacity-40"
            >
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              Сохранить изменения в анкете
            </button>
          )}

          <Link
            href="/surveys"
            className="inline-flex items-center gap-1.5 text-sm text-slate underline underline-offset-4 hover:text-foreground"
          >
            Все анкеты <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        </div>

        {loadError && (
          <p className="mt-3 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
            Не удалось прочитать список анкет: {loadError}. Шаг работает на базовых критериях.
          </p>
        )}

        {surveys?.length === 0 && !loadError && (
          <p className="mt-3 text-xs leading-relaxed text-slate">
            Сохранённых анкет нет. Прогон пойдёт по базовым критериям, и анкета будет создана
            вместе с ним — потом её можно править в разделе «Анкеты».
          </p>
        )}

        {dirty && (
          <p className="mt-3 rounded-md border border-warning/30 bg-warning-soft/60 px-3 py-2 text-xs leading-relaxed">
            Есть несохранённые правки. Без сохранения прогон пойдёт по анкете в том виде, в
            каком она лежит в разделе «Анкеты», — правки на этом экране до персон не доедут.
            Сохранение изменит анкету для всех будущих прогонов; отчёты прошлых не изменятся.
          </p>
        )}

        {saveError && (
          <p className="mt-3 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{saveError}</p>
        )}
        {savedAt !== null && !dirty && !saveError && (
          <p className="mt-3 text-xs text-slate">Анкета сохранена.</p>
        )}
      </div>

      <SurveyBuilder questions={questions} onChange={onChange} />
    </div>
  );
}
