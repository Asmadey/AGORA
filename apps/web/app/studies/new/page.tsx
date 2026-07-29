"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, ChevronLeft, ChevronRight, Upload, FileText, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { Chip } from "@/components/agora/Primitives";
import { SurveyBuilder, BASE_QUESTIONS } from "@/components/agora/SurveyBuilder";
import type { SurveyQuestion } from "@/lib/agora-types";
import { MOCK_PERSONAS } from "@/lib/mock-data";

/**
 * Визард запуска исследования (задачи #7–#11).
 *
 * В проде состоянием управляет XState и черновики сохраняются в MongoDB; здесь
 * локальное состояние — витрина потока. Порядок шагов повторяет порядок решений
 * пользователя, а не структуру бэкенда.
 */

const STEPS = ["Контент", "Аудитория", "Опрос", "Резюме"] as const;

const AGE_GROUPS = ["14-17", "18-24", "25-34", "35-44", "45-59", "60+"] as const;
const GEOS = ["столицы", "центры субъектов", "иные НП"] as const;

export default function NewStudyPage() {
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"short" | "long">("short");
  const [ages, setAges] = useState<string[]>(["25-34", "35-44", "45-59"]);
  const [geos, setGeos] = useState<string[]>(["столицы", "центры субъектов"]);
  const [size, setSize] = useState(20);
  const [replication, setReplication] = useState(1);
  const [reuseSet, setReuseSet] = useState(false);
  const [contextFile, setContextFile] = useState<string | null>(null);
  const [questions, setQuestions] = useState<SurveyQuestion[]>(BASE_QUESTIONS);

  const toggle = (arr: string[], set: (v: string[]) => void, v: string) =>
    set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  return (
    <div className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Новое исследование</h1>

      {/* Шаги */}
      <ol className="mt-6 flex items-center gap-2">
        {STEPS.map((s, i) => (
          <li key={s} className="flex flex-1 items-center gap-2">
            <button
              onClick={() => setStep(i)}
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-medium transition-colors",
                i < step && "bg-emerald-500/20 text-emerald-300",
                i === step && "bg-foreground text-background",
                i > step && "border border-border text-muted-foreground",
              )}
            >
              {i < step ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </button>
            <span
              className={cn(
                "hidden text-sm sm:block",
                i === step ? "text-foreground" : "text-muted-foreground",
              )}
            >
              {s}
            </span>
            {i < STEPS.length - 1 && <span className="h-px flex-1 bg-border" />}
          </li>
        ))}
      </ol>

      <div className="mt-8 rounded-lg border border-border bg-[hsl(222_47%_7%)] p-6">
        {/* Шаг 1 — контент */}
        {step === 0 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-sm font-semibold">Материал</h2>
              <label className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-border py-10 transition-colors hover:border-muted-foreground/50">
                <Upload className="h-6 w-6 text-muted-foreground" />
                <span className="mt-3 text-sm">Перетащите видео или выберите файл</span>
                <span className="mt-1 text-xs text-muted-foreground">
                  mp4, mov, avi · до 700 МБ
                </span>
                <input type="file" className="hidden" accept="video/mp4,video/quicktime,video/x-msvideo" />
              </label>
            </div>

            <div>
              <h2 className="text-sm font-semibold">Режим обработки</h2>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {(
                  [
                    { v: "short", t: "Короткое видео", d: "До ~10 минут. Разбор целиком." },
                    { v: "long", t: "Длинное видео", d: "Серия или фильм. Сегменты по 10 минут, map-reduce." },
                  ] as const
                ).map((o) => (
                  <button
                    key={o.v}
                    onClick={() => setMode(o.v)}
                    className={cn(
                      "rounded-md border p-4 text-left transition-colors",
                      mode === o.v ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50",
                    )}
                  >
                    <span className="block text-sm font-medium">{o.t}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">{o.d}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Шаг 2 — аудитория */}
        {step === 1 && (
          <div className="space-y-6">
            <div className="flex gap-2">
              <button
                onClick={() => setReuseSet(false)}
                className={cn(
                  "flex-1 rounded-md border p-3 text-sm transition-colors",
                  !reuseSet ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50",
                )}
              >
                Создать аудиторию
              </button>
              <button
                onClick={() => setReuseSet(true)}
                className={cn(
                  "flex-1 rounded-md border p-3 text-sm transition-colors",
                  reuseSet ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50",
                )}
              >
                Выбрать существующую
              </button>
            </div>

            {reuseSet ? (
              <div className="rounded-md border border-border p-4">
                <p className="text-sm font-medium">Ландыши, базовая аудитория</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {MOCK_PERSONAS.length} персон · seed 481502 · создана 24.07.2026
                </p>
                <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
                  Переиспользование того же набора делает результаты сопоставимыми между
                  версиями монтажа — разница в баллах будет отражать изменения материала,
                  а не разницу аудиторий.
                </p>
              </div>
            ) : (
              <>
                <div>
                  <h2 className="text-sm font-semibold">Возрастные группы</h2>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {AGE_GROUPS.map((g) => (
                      <button
                        key={g}
                        onClick={() => toggle(ages, setAges, g)}
                        className={cn(
                          "rounded-full border px-3 py-1.5 text-sm transition-colors",
                          ages.includes(g)
                            ? "border-foreground bg-secondary"
                            : "border-border text-muted-foreground hover:bg-secondary/50",
                        )}
                      >
                        {g}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <h2 className="text-sm font-semibold">География</h2>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {GEOS.map((g) => (
                      <button
                        key={g}
                        onClick={() => toggle(geos, setGeos, g)}
                        className={cn(
                          "rounded-full border px-3 py-1.5 text-sm transition-colors",
                          geos.includes(g)
                            ? "border-foreground bg-secondary"
                            : "border-border text-muted-foreground hover:bg-secondary/50",
                        )}
                      >
                        {g}
                      </button>
                    ))}
                  </div>
                  {geos.includes("иные НП") && (
                    <p className="mt-3 flex gap-2 rounded-md border border-amber-500/25 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-200/80">
                      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      Группа «иные НП» не представлена в корпусе фокус-групп (0 из 165
                      респондентов). Персоны этой группы будут сгенерированы без заземления
                      на реальные данные, и выводы по ним менее надёжны.
                    </p>
                  )}
                </div>

                <div>
                  <h2 className="text-sm font-semibold">Размер аудитории</h2>
                  <div className="mt-3 flex items-center gap-4">
                    <input
                      type="range"
                      min={5}
                      max={60}
                      step={5}
                      value={size}
                      onChange={(e) => setSize(Number(e.target.value))}
                      className="flex-1"
                    />
                    <span className="w-16 text-right text-lg font-semibold tabular-nums">{size}</span>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Рекомендуем 20 — этого хватает на сегментные срезы без лишней стоимости.
                  </p>
                </div>

                <div>
                  <h2 className="text-sm font-semibold">Дополнительный контекст</h2>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    Файл с описанием вашей аудитории уточнит персон — лексику, специфику ниши.
                    Он не переопределяет распределения и калибровку баллов: заземление на
                    корпус остаётся главным.
                  </p>
                  <label className="mt-3 flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-border px-4 py-3 transition-colors hover:border-muted-foreground/50">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm">
                      {contextFile ?? "Приложить файл (pdf, docx, md, xlsx)"}
                    </span>
                    <input
                      type="file"
                      className="hidden"
                      onChange={(e) => setContextFile(e.target.files?.[0]?.name ?? null)}
                    />
                  </label>
                </div>
              </>
            )}
          </div>
        )}

        {/* Шаг 3 — опрос */}
        {step === 2 && <SurveyBuilder questions={questions} onChange={setQuestions} />}

        {/* Шаг 4 — резюме */}
        {step === 3 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-sm font-semibold">Перекрытие</h2>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Сколько раз каждая персона проходит анкету. При значении больше 1 в отчёте
                появляется разброс оценок — видно, насколько результат устойчив. Стоимость
                прогона растёт пропорционально.
              </p>
              <div className="mt-3 flex gap-2">
                {[1, 3, 5].map((n) => (
                  <button
                    key={n}
                    onClick={() => setReplication(n)}
                    className={cn(
                      "flex-1 rounded-md border px-3 py-2.5 text-sm transition-colors",
                      replication === n
                        ? "border-foreground bg-secondary"
                        : "border-border hover:bg-secondary/50",
                    )}
                  >
                    ×{n}
                    {n === 1 && (
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        без разброса
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <dl className="space-y-2 rounded-md border border-border p-4 text-sm">
              {[
                ["Режим", mode === "short" ? "Короткое видео" : "Длинное видео"],
                ["Аудитория", reuseSet ? "Ландыши, базовая аудитория" : `${size} персон`],
                ["Возраст", reuseSet ? "—" : ages.join(", ") || "не выбран"],
                ["География", reuseSet ? "—" : geos.join(", ") || "не выбрана"],
                ["Доп. контекст", contextFile ?? "не приложен"],
                [
                  "Анкета",
                  `${questions.length} вопросов` +
                    (questions.length > BASE_QUESTIONS.length
                      ? ` (${questions.length - BASE_QUESTIONS.length} своих)`
                      : ""),
                ],
                ["Перекрытие", `×${replication}`],
                ["Вызовов модели", `≈ ${(reuseSet ? MOCK_PERSONAS.length : size) * replication + 40}`],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
            </dl>

            <div className="flex flex-wrap gap-2">
              <Chip tone="outline">Оценка времени: 8–12 минут</Chip>
              <Chip tone="outline">Лимит стоимости: авто</Chip>
            </div>

            <Link
              href="/runs/task-9a55/progress"
              className="block w-full rounded-md bg-foreground py-3 text-center text-sm font-medium text-background transition-opacity hover:opacity-90"
            >
              Запустить исследование
            </Link>
          </div>
        )}
      </div>

      {/* Навигация */}
      <div className="mt-5 flex justify-between">
        <button
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary disabled:pointer-events-none disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" />
          Назад
        </button>
        <button
          onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
          disabled={step === STEPS.length - 1}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary disabled:pointer-events-none disabled:opacity-40"
        >
          Далее
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
