"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Check, ChevronLeft, ChevronRight, Upload, FileText, Info } from "lucide-react";
import { FileChip } from "@/components/agora/FileChip";
import { UploadProgress } from "@/components/agora/UploadProgress";
import { putWithProgress, uploadPercent, type UploadState } from "@/lib/upload";
import { cn } from "@/lib/utils";
import { Chip } from "@/components/agora/Primitives";
import { SurveyBuilder, BASE_QUESTIONS } from "@/components/agora/SurveyBuilder";
import { AudienceStep } from "@/components/agora/AudienceStep";
import { ProjectPicker, type ProjectOption } from "@/components/agora/ProjectPicker";
import { DEFAULT_CRITERIA, type AudienceCriteria } from "@/lib/audience";
import type { SurveyQuestion } from "@/lib/agora-types";

/**
 * Визард запуска исследования (задачи #7–#11).
 *
 * В проде состоянием управляет XState и черновики сохраняются в MongoDB; здесь
 * локальное состояние — витрина потока. Порядок шагов повторяет порядок решений
 * пользователя, а не структуру бэкенда.
 */

const STEPS = ["Контент", "Аудитория", "Опрос", "Резюме"] as const;

const AGE_GROUPS = ["14-17", "18-24", "25-34", "35-44", "45-59", "60+"] as const;

/**
 * Обращения к модели помимо ответов персон: разбор кадров, склейка, QA,
 * аналитика. Порядок величины, а не точное число, — оно зависит от длины ролика
 * и числа сцен. Показано как «≈» именно поэтому.
 */
const PIPELINE_CALLS = 40;
const GEOS = ["столицы", "центры субъектов", "иные НП"] as const;

export default function NewStudyPage() {
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"short" | "long">("short");
  const [criteria, setCriteria] = useState<AudienceCriteria>(DEFAULT_CRITERIA);
  const [replication, setReplication] = useState(1);
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  // Идентификатор созданного исследования. Показывается до перехода в список:
  // по нему ищут прогон в логах и в поддержке, и увидеть его надо один раз, а
  // не выкапывать из адреса.
  const [launchedId, setLaunchedId] = useState<string | null>(null);
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
    // Проверка перед отправкой называет ШАГ, а не поле. Маршрут отвечает
    // «videoRef: строка либо отсутствует» — это верно и бесполезно: по такому
    // тексту непонятно, куда возвращаться. Поэтому недостающее перечисляется
    // здесь, на языке визарда, и каждая строка ведёт на свой шаг.
    if (missing.length > 0) {
      setLaunchError(null);
      setStep(missing[0].step);
      return;
    }

    setLaunching(true);
    setLaunchError(null);
    try {
      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          videoRef,
          // Имя файла — для показа в списке. Ключ S3 из него не собирается:
          // пользовательские имена содержат пробелы, кириллицу и повторяются, а
          // ключ обязан быть уникальным. Поэтому имя едет отдельным полем.
          sourceName: videoName,
          projectId,
          personaSetId,
          replicationCount: replication,
          seed,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        // `details` — список конкретных претензий маршрута. Раньше он
        // отбрасывался, и на экран попадало только «некорректные параметры»:
        // причина приезжала и не читалась. Тот же дефект, что был у судьи QA.
        const details: string[] = Array.isArray(data?.details) ? data.details : [];
        setLaunchError(
          [data?.error ?? `запуск не удался (код ${res.status})`, ...details].join("\n"),
        );
        return;
      }
      // Сначала показываем идентификатор, потом уводим в список: переход
      // сразу же прятал бы номер, ради которого его и спрашивали.
      setLaunchedId(String(data.id));
    } catch (e) {
      setLaunchError((e as Error).message);
    } finally {
      setLaunching(false);
    }
  }

  // null — «без проекта», законный выбор: у арендатора, запускающего первое
  // исследование, проектов нет вовсе, и обязательное поле означало бы
  // «сначала придумай папку, потом работай».
  const [project, setProject] = useState<ProjectOption | null>(null);
  const projectId = project?.id ?? null;
  const [personaSetId, setPersonaSetId] = useState<string | null>(null);
  // Размер выбранного набора приходит с шагом «Аудитория»: список наборов
  // загружает он, и только он знает, сколько там персон. Резюме считает по
  // этому числу оценку вызовов модели — приблизительное значение здесь
  // означало бы названную наугад стоимость прогона.
  const [personaSetSize, setPersonaSetSize] = useState<number | null>(null);
  /**
   * Критерии, по которым собран ВЫБРАННЫЙ набор.
   *
   * Резюме показывало прочерк вместо возраста и географии, как только набор был
   * выбран: критерии шага «Аудитория» к готовому набору не относятся, а его
   * собственные наверх не передавались. Прочерк при этом читается как «данных
   * нет», хотя набор описан полностью — они лежат в
   * `persona_sets.generation_config`.
   */
  const [personaSetConfig, setPersonaSetConfig] = useState<Record<string, unknown> | null>(null);
  const [contextFile, setContextFile] = useState<{ name: string; size: number } | null>(null);
  const [videoRef, setVideoRef] = useState<string | null>(null);
  const [videoName, setVideoName] = useState<string | null>(null);
  // Размер держим отдельно от File: сам объект File живёт только до
  // перерисовки, а плашке нужно показывать вес и после неё.
  const [videoSize, setVideoSize] = useState<number | null>(null);
  // Полное состояние загрузки, а не булево «идёт/не идёт». Спиннер не отличим
  // от повисшего запроса, а ролик грузится минутами.
  const [upload, setUpload] = useState<UploadState>({ phase: "idle", sent: 0, total: 0 });
  const uploading = upload.phase === "presigning" || upload.phase === "uploading" ||
    upload.phase === "checking";

  // Сколько персон реально пойдёт в прогон: размер выбранного набора либо
  // заказанный размер генерации. null — набор выбран, а его размер ещё не
  // приехал; оценка в резюме тогда честно показывает прочерк.
  const audienceSize = personaSetId ? personaSetSize : criteria.size;

  /**
   * Значение из состава выбранного набора либо null, если набор не выбран.
   *
   * Пустой список у набора — законный случай: «любой возраст» при генерации.
   * Так и пишем, а не прочерком: прочерк означает «неизвестно», а здесь
   * известно, что ограничения не было.
   */
  function setList(key: string): string | null {
    if (!personaSetId || !personaSetConfig) return null;
    const raw = personaSetConfig[key];
    if (!Array.isArray(raw)) return null;
    return raw.length ? raw.map(String).join(", ") : "без ограничения";
  }

  // Загрузка идёт по маршрутам #8, уже подтверждённым на стенде: presign → PUT
  // байтов прямо в S3 → complete с ffprobe-валидацией. Веб файл не проксирует:
  // 700 МБ через Next-роут упёрлись бы в лимит тела запроса.
  async function uploadVideo(file: File) {
    setLaunchError(null);
    // Плашка появляется до первого запроса: заливка 700 МБ идёт минуты, и всё
    // это время экран не должен выглядеть так, будто файл не приняли.
    setVideoName(file.name);
    setVideoSize(file.size);
    setUpload({ phase: "presigning", sent: 0, total: file.size });

    try {
      const pres = await fetch("/api/upload/presign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fileName: file.name, contentType: file.type, fileSize: file.size }),
      });
      const p = await pres.json();
      if (!pres.ok) throw new Error(p?.error ?? `presign вернул ${pres.status}`);

      // XMLHttpRequest, а не fetch: у fetch нет события на выгруженные байты,
      // то есть прогресс отправки недоступен принципиально. См. lib/upload.ts.
      setUpload({ phase: "uploading", sent: 0, total: file.size });
      await putWithProgress(p.uploadUrl, file, (sent, total) =>
        setUpload({ phase: "uploading", sent, total: total || file.size }),
      );

      // Последний байт ушёл — но материал ещё не принят: ffprobe проверяет
      // контейнер, кодеки и длительность и может файл отвергнуть.
      setUpload({ phase: "checking", sent: file.size, total: file.size });
      const done = await fetch("/api/upload/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: p.key, mode }),
      });
      const d = await done.json();
      if (!done.ok) throw new Error(d?.error ?? `complete вернул ${done.status}`);

      setVideoRef(d.key);
      setUpload({ phase: "done", sent: file.size, total: file.size });
    } catch (e) {
      setUpload({
        phase: "failed",
        sent: 0,
        total: file.size,
        error: (e as Error).message,
      });
    }
  }

  const [questions, setQuestions] = useState<SurveyQuestion[]>(BASE_QUESTIONS);

  const clearVideo = () => {
    setVideoRef(null);
    setVideoName(null);
    setVideoSize(null);
    setUpload({ phase: "idle", sent: 0, total: 0 });
    setLaunchError(null);
  };

  /**
   * Чего не хватает для запуска — на языке визарда, а не контракта маршрута.
   *
   * Считается на каждом рендере, поэтому список исчезает по мере заполнения:
   * пользователь видит, что действие засчитано, не нажимая «Запустить» ещё раз.
   */
  const missing: { step: number; what: string; how: string }[] = [];
  if (!videoRef) {
    missing.push({
      step: 0,
      what: "Не приложен материал",
      how: uploading
        ? (() => {
            const pct = uploadPercent(upload);
            return pct === null
              ? "Ролик ещё загружается — дождитесь окончания"
              : `Ролик загружается: ${pct}% — дождитесь окончания`;
          })()
        : upload.phase === "failed"
          ? `Загрузка не удалась: ${upload.error ?? "причина неизвестна"}. Приложите файл заново`
          : "Шаг «Контент»: выберите видео",
    });
  }
  if (!personaSetId) {
    missing.push({
      step: 1,
      what: "Не выбрана аудитория",
      how: "Шаг «Аудитория»: сгенерируйте набор персон или выберите существующий",
    });
  }
  if (questions.length === 0) {
    missing.push({
      step: 2,
      what: "Пустая анкета",
      how: "Шаг «Опрос»: нужны хотя бы пять базовых критериев",
    });
  }

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
                i < step && "bg-emerald-500/20 text-success",
                i === step && "bg-foreground text-background",
                i > step && "border border-hairline text-slate",
              )}
            >
              {i < step ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </button>
            <span
              className={cn(
                "hidden text-sm sm:block",
                i === step ? "text-foreground" : "text-slate",
              )}
            >
              {s}
            </span>
            {i < STEPS.length - 1 && <span className="h-px flex-1 bg-border" />}
          </li>
        ))}
      </ol>

      <div className="mt-8 rounded-lg border border-hairline bg-card p-6">
        {/* Шаг 1 — контент */}
        {step === 0 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-sm font-semibold">Материал</h2>

              {/* Пока файла нет — зона выбора. Как только он выбран, на её месте
                  встаёт плашка: две зоны одновременно означали бы, что можно
                  приложить второй ролик, а прогон идёт по одному. */}
              {videoName && (uploading || upload.phase === "failed") ? (
                <UploadProgress
                  className="mt-3"
                  name={videoName}
                  state={upload}
                  onCancel={clearVideo}
                />
              ) : videoName ? (
                <FileChip
                  className="mt-3"
                  kind="video"
                  name={videoName}
                  size={videoSize}
                  onRemove={clearVideo}
                />
              ) : (
                <label className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-hairline-strong py-10 transition-colors hover:border-ink/40 hover:bg-surface">
                  <Upload className="h-6 w-6 text-slate" />
                  <span className="mt-3 text-sm">Перетащите видео или выберите файл</span>
                  <span className="mt-1 text-xs text-slate">mp4, mov, avi · до 700 МБ</span>
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
              )}
            </div>

            <ProjectPicker value={projectId} onChange={setProject} />

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
                      mode === o.v ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary",
                    )}
                  >
                    <span className="block text-sm font-medium">{o.t}</span>
                    <span className="mt-1 block text-xs text-slate">{o.d}</span>
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
            onPersonaSetChange={(id, size, config) => {
              setPersonaSetId(id);
              setPersonaSetSize(size ?? null);
              setPersonaSetConfig(config ?? null);
            }}
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
              <p className="mt-1 text-xs leading-relaxed text-slate">
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
                        ? "border-ink bg-secondary"
                        : "border-hairline hover:bg-secondary",
                    )}
                  >
                    ×{n}
                    {n === 1 && (
                      <span className="mt-0.5 block text-xs text-slate">
                        без разброса
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <dl className="space-y-2 rounded-md border border-hairline p-4 text-sm">
              {[
                ["Проект", project?.name ?? "без проекта"],
                ["Режим", mode === "short" ? "Короткое видео" : "Длинное видео"],
                [
                  "Аудитория",
                  personaSetId
                    ? personaSetSize !== null
                      ? `выбранный набор, ${personaSetSize} персон`
                      : "выбранный набор персон"
                    : `${criteria.size} персон`,
                ],
                // У выбранного набора показывается ЕГО состав, а не критерии
                // этого шага: критерии описывают будущую генерацию, а прогон
                // пойдёт по уже собранному набору. Прочерк, стоявший здесь
                // раньше, читался как «данных нет», хотя набор описан целиком.
                ["Возраст", setList("age_groups") ?? (criteria.ageGroups.join(", ") || "не выбран")],
                ["География", setList("geos") ?? (criteria.geos.join(", ") || "не выбрана")],
                ["Доп. контекст", contextFile?.name ?? "не приложен"],
                [
                  "Анкета",
                  `${questions.length} вопросов` +
                    (questions.length > BASE_QUESTIONS.length
                      ? ` (${questions.length - BASE_QUESTIONS.length} своих)`
                      : ""),
                ],
                ["Перекрытие", `×${replication}`],
                [
                  "Вызовов модели",
                  // Прочерк, а не оценка по чужому числу: раньше здесь стояла
                  // длина MOCK_PERSONAS, то есть выдуманная стоимость прогона.
                  audienceSize === null
                    ? "—"
                    : `≈ ${audienceSize * replication + PIPELINE_CALLS}`,
                ],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-slate">{k}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
            </dl>

            <div className="flex flex-wrap gap-2">
              <Chip tone="outline">Оценка времени: 8–12 минут</Chip>
              <Chip tone="outline">Лимит стоимости: авто</Chip>
            </div>

            {/* Ход загрузки виден и на «Резюме»: пользователь дошёл сюда,
                пока ролик заливается, и уходить на первый шаг ради полосы
                прогресса ему незачем. */}
            {videoName && (uploading || upload.phase === "failed") && (
              <UploadProgress name={videoName} state={upload} />
            )}

            {/* Чего не хватает — до нажатия, а не после. Каждая строка ведёт
                на свой шаг: сказать «не заполнено» и оставить пользователя
                искать где — половина сообщения. */}
            {missing.length > 0 && (
              <div className="rounded-lg border border-warning/30 bg-warning-soft/60 p-4">
                <p className="text-sm font-medium">Чтобы запустить, не хватает:</p>
                <ul className="mt-2 space-y-2">
                  {missing.map((m) => (
                    <li key={m.what} className="text-sm">
                      <button
                        onClick={() => setStep(m.step)}
                        className="text-left underline decoration-dotted underline-offset-4 hover:no-underline"
                      >
                        {m.what}
                      </button>
                      <span className="block text-xs text-slate">{m.how}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {launchError && (
              <div className="rounded-lg border border-danger/30 bg-danger-soft/60 p-4">
                <p className="text-sm font-medium">Запуск не состоялся</p>
                {/* Переносы сохраняются: маршрут возвращает список претензий, и
                    склеенные в строку они читаются как одна длинная фраза. */}
                <p className="mt-1 whitespace-pre-line text-xs leading-relaxed">{launchError}</p>
              </div>
            )}

            {/* Исследование создано: показываем присвоенный номер и уводим
                дальше по кнопке, а не автоматически. */}
            {launchedId && (
              <div className="rounded-lg border border-success/30 bg-success/10 p-4">
                <p className="text-sm font-medium">Исследование создано</p>
                <p className="mt-1 font-mono text-sm break-all">{launchedId}</p>
                <p className="mt-1 text-xs leading-relaxed text-slate">
                  Разбор идёт десятки минут. По этому номеру исследование ищется в
                  списке, в логах воркера и в обращении в поддержку.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link
                    href="/researches"
                    className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-ink/90"
                  >
                    К списку исследований
                  </Link>
                  <Link
                    href={`/runs/${launchedId}/progress`}
                    className="rounded-full border border-hairline px-4 py-2 text-sm transition-colors hover:bg-surface"
                  >
                    Следить за ходом
                  </Link>
                </div>
              </div>
            )}

            <button
              onClick={launch}
              disabled={launching || launchedId !== null}
              className="block w-full rounded-full bg-primary py-3 text-center text-sm font-medium text-primary-foreground transition-colors hover:bg-ink/90 disabled:opacity-50"
            >
              {launching
                ? "Запускаем…"
                : launchedId
                  ? "Запущено"
                  : missing.length > 0
                    ? "Показать, чего не хватает"
                    : "Запустить исследование"}
            </button>
          </div>
        )}
      </div>

      {/* Навигация */}
      <div className="mt-5 flex justify-between">
        <button
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
          className="inline-flex items-center gap-1.5 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary disabled:pointer-events-none disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" />
          Назад
        </button>
        <button
          onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
          disabled={step === STEPS.length - 1}
          className="inline-flex items-center gap-1.5 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary disabled:pointer-events-none disabled:opacity-40"
        >
          Далее
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
