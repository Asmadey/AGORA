"use client";

import { Fragment, useEffect, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";

import type { CorpusDataset, CorpusRecord } from "@/lib/server/corpus-db";

/**
 * Таблица корпуса с правкой записей (этап Е).
 *
 * ─── Почему запись правится как JSON ───────────────────────────────────────
 * У карточки респондента восемь секций разной формы, и одна из них —
 * `all_survey_responses` — словарь «вопрос → ответ» на 23–53 пары, причём
 * состав вопросов задаёт исследование, а не схема. Форма с фиксированными
 * полями описала бы только сегодняшний состав и разошлась бы с корпусом на
 * первом же новом вопросе; поля пришлось бы дописывать в код каждый раз, когда
 * исследователь добавляет вопрос.
 *
 * Поэтому здесь редактор структуры целиком, с проверкой разбора перед
 * отправкой. Это честнее промежуточного варианта: форма на восемь секций
 * выглядела бы полной и молча теряла бы всё, чего в ней не предусмотрели.
 *
 * ─── Чего здесь нет ────────────────────────────────────────────────────────
 * Метрик заземления: охвата по возрасту, гео и полу, отклонения выдачи от
 * корпуса. Считать их по загруженной странице нельзя — 50 записей из 165 дадут
 * цифру, которая выглядит как метрика и ею не является, — а считать по всему
 * датасету нужен отдельный запрос с агрегатами. Он не написан, и пустого места
 * под него на экране тоже нет: заголовок «Охват корпуса» с прочерками читался
 * бы как «не заземлено».
 */

interface Props {
  datasets: CorpusDataset[];
}

const PAGE = 50;

export function CorpusBrowser({ datasets }: Props) {
  const [datasetId, setDatasetId] = useState(datasets[0]?.id ?? "");
  const [records, setRecords] = useState<CorpusRecord[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<CorpusRecord | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async (id: string, from: number) => {
    setError(null);
    const res = await fetch(`/api/corpus?datasetId=${id}&offset=${from}`);
    if (!res.ok) {
      setError(`не удалось загрузить записи (${res.status})`);
      return;
    }
    const data = (await res.json()) as {
      records: { items: CorpusRecord[]; total: number } | null;
    };
    setRecords(data.records?.items ?? []);
    setTotal(data.records?.total ?? 0);
  };

  useEffect(() => {
    if (datasetId) void load(datasetId, offset);
  }, [datasetId, offset]);

  const remove = async (record: CorpusRecord) => {
    setBusy(true);
    try {
      const res = await fetch(`/api/corpus/records?id=${record.id}`, { method: "DELETE" });
      if (!res.ok) {
        const payload = (await res.json().catch(() => ({}))) as { error?: string };
        setError(payload.error ?? `удаление не удалось (${res.status})`);
        return;
      }
      await load(datasetId, offset);
    } finally {
      setBusy(false);
    }
  };

  const save = async (respondentId: string, raw: string) => {
    let data: unknown;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      // Разбор проверяется здесь, а не на сервере: сохранить сломанный JSON
      // нельзя, а сообщение о синтаксисе полезно рядом с текстом, а не после
      // круга по сети.
      setError(`запись не разбирается как JSON: ${(e as Error).message}`);
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/corpus/records", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ datasetId, respondentId, data }),
      });
      if (!res.ok) {
        const payload = (await res.json().catch(() => ({}))) as { error?: string };
        setError(payload.error ?? `сохранение не удалось (${res.status})`);
        return;
      }
      setEditing(null);
      await load(datasetId, offset);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={datasetId}
          onChange={(e) => {
            setDatasetId(e.target.value);
            setOffset(0);
          }}
          className="rounded-md border border-hairline bg-background px-3 py-2 text-sm"
        >
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} — {d.recordsCount} записей
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={() =>
            setEditing({
              id: "",
              respondentId: "",
              data: {},
              updatedAt: new Date().toISOString(),
            })
          }
          className="inline-flex items-center gap-2 rounded-md border border-hairline px-3 py-2 text-sm transition-colors hover:bg-secondary"
        >
          <Plus className="h-4 w-4" />
          Добавить запись
        </button>

        <span className="text-xs text-slate">
          {total > 0 && `показаны ${offset + 1}–${Math.min(offset + PAGE, total)} из ${total}`}
        </span>
      </div>

      {error && (
        <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>
      )}

      {records === null ? (
        <p className="text-sm text-slate">Загружаем записи…</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-hairline">
          <table className="w-full text-sm">
            <thead className="border-b border-hairline bg-secondary text-left text-xs text-slate">
              <tr>
                <th className="px-3 py-2">Респондент</th>
                <th className="px-3 py-2">Пол</th>
                <th className="px-3 py-2">Возраст</th>
                <th className="px-3 py-2">Гео</th>
                <th className="px-3 py-2">Ответов анкеты</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {records.map((r) => {
                const socio = (r.data.socio_demographics ?? {}) as Record<string, unknown>;
                const survey = (r.data.all_survey_responses ?? {}) as Record<string, unknown>;
                const open = editing?.id === r.id;
                return (
                  /*
                    Фрагмент, а не одна строка: редактор раскрывается ПОД
                    правимой записью. Прежде он рисовался над таблицей, и
                    нажатие «Править» на сороковой строке требовало прокрутки
                    в начало страницы — чтобы увидеть, что именно правишь.
                    Связь между строкой и формой при этом держалась только
                    памятью: на экране их вместе не было никогда.
                  */
                  <Fragment key={r.id}>
                    <tr className={open ? "bg-secondary/40" : "border-b border-hairline-soft last:border-0"}>
                      <td className="px-3 py-2 font-mono text-xs">{r.respondentId}</td>
                      <td className="px-3 py-2">{String(socio.gender ?? "—")}</td>
                      <td className="px-3 py-2">{String(socio.age_group ?? socio.age ?? "—")}</td>
                      <td className="px-3 py-2">{String(socio.geo ?? "—")}</td>
                      <td className="px-3 py-2 tabular-nums">{Object.keys(survey).length}</td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => setEditing(open ? null : r)}
                          className="mr-3 text-xs underline underline-offset-4"
                        >
                          {open ? "Свернуть" : "Править"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void remove(r)}
                          disabled={busy}
                          aria-label={`Удалить ${r.respondentId}`}
                          className="text-stone transition-colors hover:text-danger disabled:opacity-40"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                    {open && (
                      <tr className="border-b border-hairline-soft last:border-0">
                        <td colSpan={6} className="bg-secondary/40 px-3 pb-4">
                          <RecordEditor
                            // key по идентификатору: без него React переиспользует
                            // состояние формы при переходе к другой записи, и в
                            // textarea остаётся карточка предыдущего респондента.
                            key={r.id}
                            record={r}
                            busy={busy}
                            onCancel={() => setEditing(null)}
                            onSave={save}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE && (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
            className="rounded-md border border-hairline px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Назад
          </button>
          <button
            type="button"
            disabled={offset + PAGE >= total}
            onClick={() => setOffset(offset + PAGE)}
            className="rounded-md border border-hairline px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Дальше
          </button>
        </div>
      )}
    </div>
  );
}

function RecordEditor({
  record,
  busy,
  onCancel,
  onSave,
}: {
  record: CorpusRecord;
  busy: boolean;
  onCancel: () => void;
  onSave: (respondentId: string, raw: string) => void;
}) {
  const [respondentId, setRespondentId] = useState(record.respondentId);
  const [raw, setRaw] = useState(JSON.stringify(record.data, null, 2));

  return (
    <div className="rounded-lg border border-hairline bg-card p-5">
      <label className="block text-xs text-slate">Идентификатор респондента</label>
      <input
        value={respondentId}
        onChange={(e) => setRespondentId(e.target.value)}
        className="mt-1 w-full rounded-md border border-hairline bg-background px-3 py-2 font-mono text-sm"
        placeholder="R-166"
      />
      <p className="mt-1 text-xs text-slate">
        Запись с уже существующим идентификатором перезаписывается: тот же
        респондент дважды удвоил бы свой вес в долях корпуса
      </p>

      <label className="mt-4 block text-xs text-slate">Карточка респондента</label>
      <textarea
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        spellCheck={false}
        rows={18}
        className="mt-1 w-full rounded-md border border-hairline bg-background px-3 py-2 font-mono text-xs"
      />

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          disabled={busy || !respondentId.trim()}
          onClick={() => onSave(respondentId.trim(), raw)}
          className="inline-flex items-center gap-2 rounded-md bg-foreground px-4 py-2 text-sm text-background disabled:opacity-40"
        >
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          Сохранить
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-hairline px-4 py-2 text-sm"
        >
          Отмена
        </button>
      </div>
    </div>
  );
}
