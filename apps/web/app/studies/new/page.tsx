"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Check, ChevronLeft, ChevronRight, Upload, FileText, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { Chip } from "@/components/agora/Primitives";
import { SurveyBuilder, BASE_QUESTIONS } from "@/components/agora/SurveyBuilder";
import { AudienceStep } from "@/components/agora/AudienceStep";
import { DEFAULT_CRITERIA, type AudienceCriteria } from "@/lib/audience";
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
  const [criteria, setCriteria] = useState<AudienceCriteria>(DEFAULT_CRITERIA);
  const [replication, setReplication] = useState(1);
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const router = useRouter();

  // Seed фиксируется ОДИН раз на сессию визарда, а не на каждый клик. Это и есть
  // рабочая идемпотентность (#11): двойное нажатие «Запустить» уходит с тем же
  // seed и возвращает ту же задачу, а новый визард даёт новый прогон.
  // Генератор в инициализаторе useState, а не в теле компонента: иначе seed
  // менялся бы на каждый ре-рендер, и защита от двойного клика не работала бы —
  // выглядя при этом рабочей.
  const [seed] = useState(() => Math.floor(Math.random() * 2 ** 31));

  // Дефолт «Перекрытия» — из Настроек арендатора (#27), а не число в коде.
  useEffect(() => {
    let alive = true;
    void fetch("/api/settings")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d?.settings?.defaultReplication) {
          setReplication(d.settings.defaultReplication as number);
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  async function launch() {
    setLaunching(true);
    setLaunchError(null);
    try {
      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          videoRef,
          personaSetId,
          replicationCount: replication,
          seed,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setLaunchError(data?.error ?? `запуск не удался (код ${res.status})`);
        return;
      }
      router.push(`/runs/${data.id}/progress`);
    } catch (e) {
      setLaunchError((e as Error).message);
    } finally {
      setLaunching(false);
    }
  }

  const [personaSetId, setPersonaSetId] = useState<string | null>(null);
  const [contextFile, setContextFile] = useState<string | null>(null);
  const [videoRef, setVideoRef] = useState<string | null>(null);
  const [videoName, setVideoName] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  // Загрузка идёт по маршрутам #8, уже подтверждённым на стенде: presign → PUT
  // байтов прямо в S3 → complete с ffprobe-валидацией. Веб файл не проксирует:
  // 700 МБ через Next-роут упёрлись бы в лимит тела запроса.
  async function uploadVideo(file: File) {
    setUploading(true);
    setLaunchError(null);
    try {
      const pres = await fetch("/api/upload/presign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fileName: file.name, contentType: file.type, fileSize: file.size }),
      });
      const p = await pres.json();
      if (!pres.ok) throw new Error(p?.error ?? `presign вернул ${pres.status}`);

      const put = await fetch(p.uploadUrl, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file,
      });
      if (!put.ok) throw new Error(`заливка в S3 вернула ${put.status}`);

      const done = await fetch("/api/upload/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: p.key, mode }),
      });
      const d = await done.json();
      if (!done.ok) throw new Error(d?.error ?? `complete вернул ${done.status}`);

      setVideoRef(d.key);
      setVideoName(file.name);
    } catch (e) {
      setLaunchError(`загрузка не удалась: ${(e as Error).message}`);
    } finally {
      setUploading(false);
    }
  }

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
                <input
                  type="file"
                  className="hidden"
                  accept="video/mp4,video/quicktime,video/x-msvideo"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void uploadVideo(f);
                  }}
                />
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
          <AudienceStep
            criteria={criteria}
            onCriteriaChange={setCriteria}
            personaSetId={personaSetId}
            onPersonaSetChange={setPersonaSetId}
            contextFile={contextFile}
            onContextFileChange={setContextFile}
          />
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
                ["Аудитория", personaSetId ? "выбранный набор персон" : `${criteria.size} персон`],
                ["Возраст", personaSetId ? "—" : criteria.ageGroups.join(", ") || "не выбран"],
                ["География", personaSetId ? "—" : criteria.geos.join(", ") || "не выбрана"],
                ["Доп. контекст", contextFile ?? "не приложен"],
                [
                  "Анкета",
                  `${questions.length} вопросов` +
                    (questions.length > BASE_QUESTIONS.length
                      ? ` (${questions.length - BASE_QUESTIONS.length} своих)`
                      : ""),
                ],
                ["Перекрытие", `×${replication}`],
                ["Вызовов модели", `≈ ${(personaSetId ? MOCK_PERSONAS.length : criteria.size) * replication + 40}`],
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

            {launchError && (
              <p className="rounded-md border border-red-500/25 bg-red-500/5 p-3 text-xs text-red-200/80">
                {launchError}
              </p>
            )}

            <button
              onClick={launch}
              disabled={launching}
              className="block w-full rounded-md bg-foreground py-3 text-center text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {launching ? "Запускаем…" : "Запустить исследование"}
            </button>
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
