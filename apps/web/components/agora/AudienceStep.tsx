"use client";

import { useEffect, useState } from "react";
import { FileText, Info, Loader2 } from "lucide-react";
import { FileChip } from "@/components/agora/FileChip";

import {
  AGE_GROUPS,
  AUDIENCE_SIZE_BOUNDS,
  GENDERS,
  GEOS,
  type AudienceCriteria,
} from "@/lib/audience";
import { cn } from "@/lib/utils";

/**
 * Шаг «Аудитория» визарда (задача #9).
 *
 * ─── Пометки заземления приходят с сервера ─────────────────────────────────
 * Раньше предупреждение про «иные НП» было строкой в разметке с числом «0 из
 * 165» внутри. Строка перестанет быть правдой в день, когда в корпус добавят
 * исследование, — а паспорт корпуса прямо описывает процедуру добавления, то
 * есть это ожидаемое событие. Теперь охват считается на сервере из самого
 * корпуса (lib/audience-grounding.ts), и тем же механизмом ловится второй
 * незаземлённый критерий, о котором в разметке не было ни слова: поля education
 * в корпусе нет ни у одной записи.
 *
 * ─── Почему пол обязателен ─────────────────────────────────────────────────
 * В корпусе он распределён 110/55 и участвует в калибровке, но до этой задачи
 * в визарде его не было вовсе. Критерий, который пользователь считает заданным,
 * а система игнорирует, хуже отсутствующего.
 */

interface CriterionCoverage {
  value: string;
  records: number;
  level: "grounded" | "thin" | "absent";
}

interface Grounding {
  totalRecords: number;
  ageGroups: CriterionCoverage[];
  geos: CriterionCoverage[];
  genders: CriterionCoverage[];
  ungroundedDimensions: string[];
}

interface PersonaSetSummary {
  id: string;
  name: string;
  size: number;
  seed: number | null;
  createdAt: string;
  personaCount: number;
  status: "generating" | "ready" | "failed";
  generatedCount: number;
  error: string | null;
}

export interface AudienceStepProps {
  criteria: AudienceCriteria;
  onCriteriaChange: (next: AudienceCriteria) => void;
  personaSetId: string | null;
  /**
   * Размер передаётся вместе с идентификатором, а не доискивается вызывающим.
   *
   * Список наборов загружает этот шаг, и он единственный знает, сколько персон
   * в выбранном. Резюме показывает по этому числу оценку вызовов модели, и
   * подставить туда что-то приблизительное значило бы назвать пользователю
   * стоимость прогона наугад.
   */
  onPersonaSetChange: (id: string | null, size?: number) => void;
  /** Приложенный файл контекста: имя и размер для плашки. */
  contextFile: { name: string; size: number } | null;
  onContextFileChange: (file: { name: string; size: number } | null) => void;
}

function toggle<T extends string>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/** Что вернула генерация. Нужно, чтобы показать результат, не перезагружая шаг. */
interface GenerationOutcome {
  personaSetId: string;
  size: number;
  enrichment: { enriched: boolean; llm_calls: number; degraded_reason?: string | null };
}

/** Подпись охвата под группой чипов. Показывается только когда есть что сказать. */
function coverageNote(rows: CriterionCoverage[], picked: string[], total: number) {
  const problems = rows.filter((r) => picked.includes(r.value) && r.level !== "grounded");
  if (problems.length === 0) return null;
  return (
    <p className="mt-3 flex gap-2 rounded-md border border-warning/30 bg-warning-soft/60 p-3 text-xs leading-relaxed text-warning">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>
        {problems.map((r) => (
          <span key={r.value} className="block">
            «{r.value}» —{" "}
            {r.records === 0
              ? `нет ни одной записи из ${total}: персоны этого сегмента не заземлены и остаются догадкой`
              : `всего ${r.records} записей из ${total}: заземление слабое, доли по сегменту неустойчивы`}
          </span>
        ))}
      </span>
    </p>
  );
}

export function AudienceStep({
  criteria,
  onCriteriaChange,
  personaSetId,
  onPersonaSetChange,
  contextFile,
  onContextFileChange,
}: AudienceStepProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [generated, setGenerated] = useState<GenerationOutcome | null>(null);
  const [grounding, setGrounding] = useState<Grounding | null>(null);
  const [sets, setSets] = useState<PersonaSetSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reuse = personaSetId !== null;

  const refreshSets = async () => {
    const r = await fetch("/api/persona-sets");
    if (!r.ok) return;
    const data = (await r.json()) as { personaSets: PersonaSetSummary[] };
    setSets(data.personaSets);
  };

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const [g, s] = await Promise.all([
          fetch("/api/audience").then((r) => (r.ok ? r.json() : null)),
          fetch("/api/persona-sets").then((r) => (r.ok ? r.json() : null)),
        ]);
        if (!alive) return;
        if (g) setGrounding(g as Grounding);
        if (s) setSets((s as { personaSets: PersonaSetSummary[] }).personaSets);
      } catch (e) {
        // Отказ загрузки не должен ломать шаг: критерии выбираются и без пометок,
        // просто без подсказки о заземлении. Но молчать нельзя — иначе
        // отсутствие предупреждений читается как «всё заземлено».
        if (alive) setLoadError((e as Error).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  /**
   * Пока хоть один набор наполняется — опрашиваем список.
   *
   * Опрос, а не SSE: канал прогресса привязан к строке `tasks` (и проверка
   * владения там же), а набор персон — не прогон. Заводить второй транспорт
   * ради одного числа дороже, чем спросить список раз в две секунды: генерация
   * идёт минуты, и запрос на этом фоне ничего не стоит.
   */
  const generating = (sets ?? []).some((s) => s.status === "generating");
  useEffect(() => {
    if (!generating) return;
    const timer = setInterval(() => void refreshSets(), 2000);
    return () => clearInterval(timer);
  }, [generating]);

  const set = (patch: Partial<AudienceCriteria>) => {
    // Правка критериев обесценивает ранее созданный набор: показывать «готово
    // 20 персон» рядом с изменёнными галочками значило бы обещать то, чего в
    // наборе нет.
    if (generated) {
      setGenerated(null);
      onPersonaSetChange(null);
    }
    onCriteriaChange({ ...criteria, ...patch });
  };

  /**
   * Генерация аудитории по критериям.
   *
   * Здесь замыкается цепочка «критерии → генератор → набор → запуск». До этой
   * правки шаг только складывал критерии в черновик, а POST не делал никто:
   * маршрут /api/audience существовал и работал, но вызвать его было некому.
   */
  const generate = async () => {
    // Повторное нажатие во время работы — это второй оплаченный прогон модели,
    // а не просто дубль запроса. Поэтому защита стоит здесь, а не только на
    // атрибуте disabled: атрибут снимается разметкой, состояние — нет.
    if (isGenerating) return;
    setIsGenerating(true);
    setGenError(null);
    try {
      const res = await fetch("/api/audience", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Тело плоское: parseAudienceChoice читает size/ageGroups/geos/genders
        // с верхнего уровня и различает ветки по наличию personaSetId, а не по
        // полю-дискриминатору.
        body: JSON.stringify(criteria),
      });
      const data = (await res.json()) as Record<string, unknown>;
      if (!res.ok) {
        throw new Error((data.error as string) ?? `генерация не удалась (${res.status})`);
      }

      // Набор заведён, персон в нём ещё нет: их пишет воркер. Переключаемся на
      // вкладку с существующими наборами — там видно, как он наполняется.
      // Раньше здесь ждали конца генерации, и на шестидесяти персонах маршрут
      // просто отваливался по таймауту, теряя всё написанное.
      const newId = data.personaSetId as string;
      onPersonaSetChange(newId, 0);
      await refreshSets();
    } catch (e) {
      setGenError((e as Error).message);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex gap-2">
        <button
          onClick={() => onPersonaSetChange(null)}
          className={cn(
            "flex-1 rounded-md border p-3 text-sm transition-colors",
            !reuse ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary",
          )}
        >
          Создать аудиторию
        </button>
        <button
          onClick={() => onPersonaSetChange(sets?.[0]?.id ?? null, sets?.[0]?.personaCount)}
          disabled={!sets || sets.length === 0}
          className={cn(
            "flex-1 rounded-md border p-3 text-sm transition-colors disabled:opacity-40",
            reuse ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary",
          )}
        >
          Выбрать существующую
          {sets && sets.length === 0 && " (пока нет наборов)"}
        </button>
      </div>

      {loadError && (
        <p className="rounded-md border border-danger/30 bg-danger-soft/60 p-3 text-xs text-danger">
          Не удалось загрузить данные о заземлении: {loadError}. Пометки о слабо
          заземлённых сегментах показаны не будут — это не значит, что их нет.
        </p>
      )}

      {reuse ? (
        <div className="space-y-2">
          {/* Список ограничен по высоте пятью плашками, и скролл — внутри него.
              Без ограничения десяток наборов уводил кнопку «Дальше» за пределы
              экрана: пользователь прокручивал всю страницу, терял из виду шаги
              визарда и не понимал, где закончился выбор. Высота задана в тех же
              единицах, что и плашка (5 × 76px + зазоры), а не «на глаз»: иначе
              она разъедется при первой же правке содержимого плашки. */}
          <div
            className={cn(
              "space-y-2 overflow-y-auto pr-1",
              (sets?.length ?? 0) > 5 && "max-h-[420px]",
            )}
          >
            {(sets ?? []).map((s) => (
              <button
                key={s.id}
                onClick={() => onPersonaSetChange(s.id, s.personaCount)}
                // Набор в работе выбрать нельзя: запуск на неполной аудитории
                // дал бы отчёт по случайной её части, и понять это было бы
                // неоткуда — размер в резюме показал бы заказанное число.
                disabled={s.status === "generating"}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg border p-4 text-left transition-colors",
                  personaSetId === s.id
                    ? "border-ink bg-secondary"
                    : "border-hairline hover:bg-secondary",
                  s.status === "generating" && "cursor-wait",
                  s.status === "failed" && "border-danger/40",
                )}
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">{s.name}</span>
                  <span className="mt-1 block text-xs text-slate">
                    {s.status === "generating" ? (
                      // Числами, а не долей: «60%» одинаково выглядит на пяти
                      // персонах и на пятистах, а ждать их надо по-разному.
                      <>Создаётся: {s.generatedCount} из {s.size}</>
                    ) : s.status === "failed" ? (
                      <span className="text-danger">
                        Генерация не удалась{s.error ? `: ${s.error}` : ""}
                      </span>
                    ) : (
                      <>
                        {s.personaCount} персон
                        {s.seed !== null && ` · seed ${s.seed}`} ·{" "}
                        {new Date(s.createdAt).toLocaleDateString("ru-RU")}
                      </>
                    )}
                  </span>
                </span>

                {s.status === "generating" && (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin text-slate" />
                )}
              </button>
            ))}
          </div>

          {(sets?.length ?? 0) > 5 && (
            <p className="pt-1 text-xs text-stone">
              Показаны {Math.min(5, sets?.length ?? 0)} из {sets?.length} — остальные
              прокруткой внутри списка
            </p>
          )}

          <p className="mt-3 text-xs leading-relaxed text-slate">
            Генерация будет пропущена: набор берётся целиком, вместе с его seed. Это
            делает результаты сопоставимыми между версиями монтажа — разница в баллах
            отражает изменения материала, а не разницу аудиторий.
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
                  onClick={() => set({ ageGroups: toggle(criteria.ageGroups, g) })}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm transition-colors",
                    criteria.ageGroups.includes(g)
                      ? "border-ink bg-secondary"
                      : "border-hairline text-slate hover:bg-secondary",
                  )}
                >
                  {g}
                </button>
              ))}
            </div>
            {grounding &&
              coverageNote(grounding.ageGroups, criteria.ageGroups, grounding.totalRecords)}
          </div>

          <div>
            <h2 className="text-sm font-semibold">Пол</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {GENDERS.map((g) => (
                <button
                  key={g}
                  onClick={() => set({ genders: toggle(criteria.genders, g) })}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm transition-colors",
                    criteria.genders.includes(g)
                      ? "border-ink bg-secondary"
                      : "border-hairline text-slate hover:bg-secondary",
                  )}
                >
                  {g}
                </button>
              ))}
            </div>
            {grounding &&
              coverageNote(grounding.genders, criteria.genders, grounding.totalRecords)}
          </div>

          <div>
            <h2 className="text-sm font-semibold">География</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {GEOS.map((g) => (
                <button
                  key={g}
                  onClick={() => set({ geos: toggle(criteria.geos, g) })}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm transition-colors",
                    criteria.geos.includes(g)
                      ? "border-ink bg-secondary"
                      : "border-hairline text-slate hover:bg-secondary",
                  )}
                >
                  {g}
                </button>
              ))}
            </div>
            {grounding && coverageNote(grounding.geos, criteria.geos, grounding.totalRecords)}
          </div>

          {/* Здесь был выбор образования. Убран, а не отключён.
              Поля education нет ни у одной из 165 записей корпуса — заземлить
              критерий нечем, и persona_grounding его не проверяет. Прежде экран
              честно писал это предупреждением под выбором, но предупреждение не
              лечит: пользователь всё равно заполняет поле, потому что оно есть,
              и получает персон, чьё «высшее образование» ничем не подкреплено.
              Поле, обещающее влияние на результат, хуже отсутствующего. */}

          <div>
            <h2 className="text-sm font-semibold">Размер аудитории</h2>
            <div className="mt-3 flex items-center gap-4">
              <input
                type="range"
                min={AUDIENCE_SIZE_BOUNDS.min}
                max={60}
                step={1}
                value={criteria.size}
                onChange={(e) => set({ size: Number(e.target.value) })}
                className="flex-1"
              />
              <span className="w-16 text-right text-lg font-semibold tabular-nums">
                {criteria.size}
              </span>
            </div>
            <p className="mt-2 text-xs text-slate">
              Рекомендуем 20 — этого хватает на сегментные срезы без лишней стоимости.
            </p>
          </div>

          <div>
            <h2 className="text-sm font-semibold">Дополнительный контекст</h2>
            <p className="mt-1 text-xs leading-relaxed text-slate">
              Файл с описанием вашей аудитории уточнит персон — лексику, специфику ниши.
              Он не переопределяет распределения и калибровку баллов: заземление на
              корпус остаётся главным.
            </p>
            {/* Как и у ролика: пока файла нет — зона выбора, после — плашка с
                именем, весом и крестиком. Прежде здесь менялась только подпись
                внутри той же рамки, и снять уже приложенный файл было нечем. */}
            {contextFile ? (
              <FileChip
                className="mt-3"
                name={contextFile.name}
                size={contextFile.size}
                onRemove={() => onContextFileChange(null)}
              />
            ) : (
              <label className="mt-3 flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-hairline-strong px-4 py-3 transition-colors hover:border-ink/40 hover:bg-surface">
                <FileText className="h-4 w-4 text-slate" />
                <span className="text-sm">Приложить файл (pdf, docx, md, xlsx)</span>
                <input
                  type="file"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    onContextFileChange(f ? { name: f.name, size: f.size } : null);
                  }}
                />
              </label>
            )}
          </div>

          <div className="border-t border-hairline pt-6">
            <button
              onClick={generate}
              disabled={isGenerating}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-foreground px-4 py-3 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {isGenerating && <Loader2 className="h-4 w-4 animate-spin" />}
              {isGenerating
                ? "Генерируем аудиторию…"
                : `Создать аудиторию из ${criteria.size} персон`}
            </button>

            {genError && (
              <p className="mt-3 rounded-md border border-danger/30 bg-danger-soft/60 p-3 text-xs leading-relaxed text-danger">
                {genError}
              </p>
            )}

            {generated && (
              <div className="mt-3 rounded-md border border-emerald-500/25 bg-success/10 p-3 text-xs leading-relaxed text-emerald-200/80">
                <p>
                  Готово: {generated.size} персон сохранено. Набор подставлен в запуск —
                  менять критерии больше не нужно.
                </p>
                {/* Деградация до шаблонных портретов обязана быть видна здесь, а
                    не только в логах: заземление персон при этом не пострадало,
                    но читаются они заметно суше, и пользователь вправе понимать,
                    почему. */}
                {!generated.enrichment?.enriched && (
                  <p className="mt-2 text-warning">
                    Портреты собраны по шаблону: модель не отвечала
                    {generated.enrichment?.degraded_reason
                      ? ` (${generated.enrichment.degraded_reason})`
                      : ""}
                    . Соцдем, ценности и баллы заземлены на корпус как обычно.
                  </p>
                )}
              </div>
            )}
          </div>
        </>
      )}

      {!grounding && !loadError && (
        <p className="flex items-center gap-2 text-xs text-slate">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Считаем охват критериев по корпусу…
        </p>
      )}
    </div>
  );
}
