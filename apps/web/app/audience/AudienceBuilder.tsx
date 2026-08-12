"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Plus } from "lucide-react";

import { ErrorState } from "@/components/agora/States";
import {
  AGE_GROUPS,
  AUDIENCE_SIZE_BOUNDS,
  DEFAULT_AUDIENCE_SIZE,
  GENDERS,
  GEOS,
} from "@/lib/audience";

/**
 * Конструктор набора персон.
 *
 * Генерация идёт тем же путём, что шаг визарда: `POST /api/audience` →
 * заземлённый на корпус генератор → набор сохраняется в базе арендатора.
 * Прежняя версия делала то же самое, но результат складывала ещё и в
 * localforage — и список на экране читала оттуда. Набор попадал в базу, экран
 * показывал копию из вкладки, и расхождение между ними ничем не проявлялось,
 * пока кто-то не открывал страницу с другой машины.
 *
 * Критерии «доход», «профессия» и свободные требования не предлагаются: в
 * корпусе таких полей нет ни у одной из 165 записей, заземлить их нечем. Поле,
 * которое пользователь заполняет, а генератор игнорирует, хуже отсутствующего —
 * оно обещает влияние на результат и создаёт доверие к персонам, которого те
 * не заслуживают.
 */

const SELECT_CLASS =
  "w-full rounded-md border border-hairline bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-muted-foreground/60";

export function AudienceBuilder() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const [size, setSize] = useState(String(DEFAULT_AUDIENCE_SIZE));
  const [age, setAge] = useState("all");
  const [gender, setGender] = useState("all");
  const [geo, setGeo] = useState("all");

  async function generate() {
    setBusy(true);
    setErrors([]);
    try {
      const res = await fetch("/api/audience", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          size: Number(size) || DEFAULT_AUDIENCE_SIZE,
          // «Все» означает весь диапазон, а не пустой список: контракт
          // отвергает пустой как незаполненный критерий.
          ageGroups: age !== "all" ? [age] : [...AGE_GROUPS],
          geos: geo !== "all" ? [geo] : [...GEOS],
          genders: gender !== "all" ? [gender] : [...GENDERS],
        }),
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

      setOpen(false);
      // Список рисует серверный компонент — обновляем его, а не собственное
      // состояние. Локальная копия и была тем, что расходилось с базой.
      router.refresh();
    } catch (error) {
      setErrors([`Запрос не дошёл: ${(error as Error).message}`]);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
      >
        <Plus className="h-4 w-4" />
        Сгенерировать набор
      </button>
    );
  }

  return (
    <div className="w-full max-w-xl rounded-lg border border-hairline bg-card p-6">
      <h2 className="text-sm font-semibold">Новый набор персон</h2>
      <p className="mt-1 text-xs leading-relaxed text-slate">
        Персоны собираются по реальным долям исследовательского корпуса из 165
        респондентов. Чем уже критерии, тем меньше записей их подпирает.
      </p>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label htmlFor="a-size" className="block text-xs text-slate">
            Размер
          </label>
          <input
            id="a-size"
            type="number"
            min={AUDIENCE_SIZE_BOUNDS.min}
            max={AUDIENCE_SIZE_BOUNDS.max}
            value={size}
            onChange={(e) => setSize(e.target.value)}
            className={SELECT_CLASS}
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="a-age" className="block text-xs text-slate">
            Возраст
          </label>
          {/* Группы берутся из контракта, а не переписываются здесь: список,
              разошедшийся с корпусом, отправляет в генератор значение, которого
              тот не знает, — то есть заведомо отвергаемый запрос. */}
          <select id="a-age" value={age} onChange={(e) => setAge(e.target.value)} className={SELECT_CLASS}>
            <option value="all">Любой (репрезентативно)</option>
            {AGE_GROUPS.map((g) => (
              <option key={g} value={g}>{g}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="a-gender" className="block text-xs text-slate">
            Пол
          </label>
          <select id="a-gender" value={gender} onChange={(e) => setGender(e.target.value)} className={SELECT_CLASS}>
            <option value="all">Смешанный</option>
            {GENDERS.map((g) => (
              <option key={g} value={g}>
                {g === "муж" ? "Только мужчины" : "Только женщины"}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="a-geo" className="block text-xs text-slate">
            Гео
          </label>
          <select id="a-geo" value={geo} onChange={(e) => setGeo(e.target.value)} className={SELECT_CLASS}>
            <option value="all">Вся Россия</option>
            {GEOS.map((g) => (
              <option key={g} value={g}>{g}</option>
            ))}
          </select>
        </div>
      </div>

      {geo === "иные НП" && (
        <p className="mt-4 rounded-md border border-warning/30 bg-warning-soft/60 px-3 py-2 text-xs leading-relaxed text-warning">
          «Иные НП» в корпусе не представлены — 0 записей из 165. Генерация по
          этому критерию заземлить персон не на чем и будет отвергнута.
        </p>
      )}

      {errors.length > 0 && (
        <div className="mt-4">
          <ErrorState title="Набор не создан" reason={errors.join("\n")} />
        </div>
      )}

      <div className="mt-5 flex items-center gap-2">
        <button
          type="button"
          onClick={generate}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          {busy ? `Генерация (${size})…` : "Создать"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          disabled={busy}
          className="rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary disabled:opacity-40"
        >
          Отмена
        </button>
      </div>
    </div>
  );
}
