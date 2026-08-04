"use client";

import { useEffect, useState } from "react";
import { FileText, Info, Loader2 } from "lucide-react";

import {
  AGE_GROUPS,
  AUDIENCE_SIZE_BOUNDS,
  EDUCATION_LEVELS,
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
}

export interface AudienceStepProps {
  criteria: AudienceCriteria;
  onCriteriaChange: (next: AudienceCriteria) => void;
  personaSetId: string | null;
  onPersonaSetChange: (id: string | null) => void;
  contextFile: string | null;
  onContextFileChange: (name: string | null) => void;
}

function toggle<T extends string>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/** Подпись охвата под группой чипов. Показывается только когда есть что сказать. */
function coverageNote(rows: CriterionCoverage[], picked: string[], total: number) {
  const problems = rows.filter((r) => picked.includes(r.value) && r.level !== "grounded");
  if (problems.length === 0) return null;
  return (
    <p className="mt-3 flex gap-2 rounded-md border border-amber-500/25 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-200/80">
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
  const [grounding, setGrounding] = useState<Grounding | null>(null);
  const [sets, setSets] = useState<PersonaSetSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reuse = personaSetId !== null;

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

  const set = (patch: Partial<AudienceCriteria>) => onCriteriaChange({ ...criteria, ...patch });

  return (
    <div className="space-y-6">
      <div className="flex gap-2">
        <button
          onClick={() => onPersonaSetChange(null)}
          className={cn(
            "flex-1 rounded-md border p-3 text-sm transition-colors",
            !reuse ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50",
          )}
        >
          Создать аудиторию
        </button>
        <button
          onClick={() => onPersonaSetChange(sets?.[0]?.id ?? null)}
          disabled={!sets || sets.length === 0}
          className={cn(
            "flex-1 rounded-md border p-3 text-sm transition-colors disabled:opacity-40",
            reuse ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50",
          )}
        >
          Выбрать существующую
          {sets && sets.length === 0 && " (пока нет наборов)"}
        </button>
      </div>

      {loadError && (
        <p className="rounded-md border border-red-500/25 bg-red-500/5 p-3 text-xs text-red-200/80">
          Не удалось загрузить данные о заземлении: {loadError}. Пометки о слабо
          заземлённых сегментах показаны не будут — это не значит, что их нет.
        </p>
      )}

      {reuse ? (
        <div className="space-y-2">
          {(sets ?? []).map((s) => (
            <button
              key={s.id}
              onClick={() => onPersonaSetChange(s.id)}
              className={cn(
                "w-full rounded-md border p-4 text-left transition-colors",
                personaSetId === s.id
                  ? "border-foreground bg-secondary"
                  : "border-border hover:bg-secondary/50",
              )}
            >
              <p className="text-sm font-medium">{s.name}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {s.personaCount} персон
                {s.seed !== null && ` · seed ${s.seed}`} ·{" "}
                {new Date(s.createdAt).toLocaleDateString("ru-RU")}
              </p>
            </button>
          ))}
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
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
                      ? "border-foreground bg-secondary"
                      : "border-border text-muted-foreground hover:bg-secondary/50",
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
                      ? "border-foreground bg-secondary"
                      : "border-border text-muted-foreground hover:bg-secondary/50",
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
                      ? "border-foreground bg-secondary"
                      : "border-border text-muted-foreground hover:bg-secondary/50",
                  )}
                >
                  {g}
                </button>
              ))}
            </div>
            {grounding && coverageNote(grounding.geos, criteria.geos, grounding.totalRecords)}
          </div>

          <div>
            <h2 className="text-sm font-semibold">
              Образование <span className="text-muted-foreground">— необязательно</span>
            </h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {EDUCATION_LEVELS.map((g) => (
                <button
                  key={g}
                  onClick={() => set({ education: toggle(criteria.education, g) })}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm transition-colors",
                    criteria.education.includes(g)
                      ? "border-foreground bg-secondary"
                      : "border-border text-muted-foreground hover:bg-secondary/50",
                  )}
                >
                  {g}
                </button>
              ))}
            </div>
            {criteria.education.length > 0 &&
              grounding?.ungroundedDimensions.includes("education") && (
                <p className="mt-3 flex gap-2 rounded-md border border-amber-500/25 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-200/80">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  В корпусе нет поля «образование» ни у одной из {grounding.totalRecords}{" "}
                  записей. Критерий повлияет на текст персон, но не на заземление, и
                  метрика persona_grounding его не проверяет.
                </p>
              )}
          </div>

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
                onChange={(e) => onContextFileChange(e.target.files?.[0]?.name ?? null)}
              />
            </label>
          </div>
        </>
      )}

      {!grounding && !loadError && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Считаем охват критериев по корпусу…
        </p>
      )}
    </div>
  );
}
