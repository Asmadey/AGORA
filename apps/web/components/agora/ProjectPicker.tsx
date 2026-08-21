"use client";

import { useEffect, useState } from "react";
import { FolderPlus, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Выбор проекта для нового исследования — шаг «Контент».
 *
 * ─── Что здесь чинится ─────────────────────────────────────────────────────
 * `tasks.project_id` есть в схеме с самого начала, `POST /api/tasks` принимает
 * `projectId` и пишет его. Визард не отправлял это поле ни разу, поэтому каждое
 * исследование, созданное через интерфейс, ложилось в базу с `project_id =
 * NULL`, а раздел «Проекты» оставался пустым при любом числе прогонов.
 *
 * Механизм был цел на всех уровнях, кроме того единственного, через который им
 * пользуются, — и статические проверки такое пропускают по построению: колонка,
 * маршрут и запись на месте, не хватает только вызывающего.
 *
 * ─── Почему проект необязателен ────────────────────────────────────────────
 * У арендатора, запускающего первое исследование, проектов нет вообще, и
 * обязательное поле означало бы «сначала придумай папку, потом работай».
 * Поэтому «Без проекта» — явный выбор в списке, а не умолчание исподтишка.
 *
 * Умолчания «положить в последний проект» здесь нет намеренно: молча
 * подшитое не туда исследование ищут потом дольше, чем кладут руками.
 */

export interface ProjectOption {
  id: string;
  name: string;
}

export function ProjectPicker({
  value,
  onChange,
}: {
  value: string | null;
  /**
   * Отдаёт весь проект, а не один идентификатор: «Резюме» показывает название,
   * и по идентификатору его пришлось бы искать вторым запросом — за данными,
   * которые уже здесь.
   */
  onChange: (project: ProjectOption | null) => void;
}) {
  const [projects, setProjects] = useState<ProjectOption[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/projects")
      .then(async (r) => {
        if (!r.ok) throw new Error(`сервер ответил ${r.status}`);
        return (await r.json()) as { projects: ProjectOption[] };
      })
      .then((d) => alive && setProjects(d.projects))
      .catch((e: Error) => {
        if (!alive) return;
        setError(e.message);
        // Пустой список, а не null: иначе экран навсегда останется на
        // «Загружаем проекты…», и запустить исследование будет нельзя из-за
        // сбоя в необязательном поле.
        setProjects([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  async function create() {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = (await res.json()) as { project?: ProjectOption; error?: string };
      if (!res.ok || !data.project) {
        setError(data.error ?? `создать проект не удалось (${res.status})`);
        return;
      }
      setProjects((list) => [data.project!, ...(list ?? [])]);
      onChange(data.project);
      setCreating(false);
      setNewName("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2 className="text-sm font-semibold">Проект</h2>
      <p className="mt-1 text-xs text-slate">
        Исследование закрепится за проектом и появится в его карточке. Можно
        оставить без проекта и перенести позже.
      </p>

      {projects === null ? (
        <p className="mt-3 text-sm text-slate">Загружаем проекты…</p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onChange(null)}
            className={cn(
              "rounded-md border px-3 py-1.5 text-sm transition-colors",
              value === null ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary",
            )}
          >
            Без проекта
          </button>

          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => onChange(p)}
              className={cn(
                "rounded-md border px-3 py-1.5 text-sm transition-colors",
                value === p.id ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary",
              )}
            >
              {p.name}
            </button>
          ))}

          {!creating && (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-hairline px-3 py-1.5 text-sm text-slate transition-colors hover:border-hairline-strong hover:text-foreground"
            >
              <FolderPlus className="h-3.5 w-3.5" />
              Создать проект
            </button>
          )}
        </div>
      )}

      {creating && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            autoFocus
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void create();
              if (e.key === "Escape") setCreating(false);
            }}
            placeholder="Название проекта"
            className="min-w-0 flex-1 rounded-md border border-hairline bg-background px-3 py-1.5 text-sm"
          />
          <button
            type="button"
            disabled={busy || !newName.trim()}
            onClick={() => void create()}
            className="inline-flex items-center gap-2 rounded-md bg-foreground px-3 py-1.5 text-sm text-background disabled:opacity-40"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Создать
          </button>
          <button
            type="button"
            onClick={() => {
              setCreating(false);
              setNewName("");
            }}
            className="rounded-md border border-hairline px-3 py-1.5 text-sm"
          >
            Отмена
          </button>
        </div>
      )}

      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}
