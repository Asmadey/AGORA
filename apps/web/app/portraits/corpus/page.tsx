import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { requireSession } from "@/lib/server/guard";
import { loadMeta, loadSessions } from "@/lib/server/corpus";
import { RespondentCard } from "./RespondentCard";

/**
 * Корпус: что на самом деле лежит под портретами.
 *
 * ─── Зачем экран нужен ─────────────────────────────────────────────────────
 * Портрет аудитории — это сжатие корпуса, а корпус до сих пор был невидим.
 * Пользователь читал «в основном женщины 35–44, ценят семью» и не имел способа
 * проверить, откуда это взялось: сколько человек за этим стоит, что они
 * отвечали, не додумала ли модель половину при дистилляции.
 *
 * Особенно это касается формы данных. У одного респондента не один ответ, а
 * целая сессия: до 53 пар «вопрос → ответ» в анкете плюс реплики фокус-группы.
 * Портрет сводит всё это в несколько абзацев, и потеря по дороге неизбежна —
 * увидеть, что именно потеряно, можно только рядом с исходником.
 *
 * ─── Почему только чтение ──────────────────────────────────────────────────
 * Корпус — файл под git с контрольной суммой в `corpus.meta.json`, и метрика
 * `persona_grounding` считается по нему. Правка из интерфейса означала бы, что
 * заземление меняется без коммита и незаметно для всех, кто прогонял раньше.
 */

export const dynamic = "force-dynamic";

export default async function CorpusPage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string }>;
}) {
  await requireSession();
  const { source } = await searchParams;

  const meta = loadMeta();
  const all = loadSessions();
  const sources = [...new Set(all.map((s) => s.source_file))].sort();
  const rows = source ? all.filter((s) => s.source_file === source) : all;

  // Показываем не всё сразу: 165 карточек с полусотней ответов каждая — это
  // мегабайты разметки на первый экран ради данных, которые смотрят выборочно.
  const PAGE = 30;
  const shown = rows.slice(0, PAGE);

  return (
    <>
      <PageHeader
        title="Корпус исследований"
        subtitle={`${meta.records} респондентов из ${sources.length} исследований — то, на чём заземлены персоны и из чего дистиллированы портреты`}
        actions={
          <Link
            href="/portraits"
            className="inline-flex items-center gap-2 rounded-full border border-hairline px-4 py-2 text-sm transition-colors hover:bg-surface"
          >
            <ArrowLeft className="h-4 w-4" />К портретам
          </Link>
        }
      />

      <div className="space-y-6 p-8">
        <section className="rounded-xl border border-hairline bg-card p-5">
          <h2 className="text-sm font-semibold">Как устроена запись</h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate">
            Одна запись — это одна сессия одного человека, а не один ответ. Внутри неё
            структурированные срезы (соцдем, ценности, пять базовых баллов, удержание),
            развёрнутые реплики и полная анкета целиком: от 23 до 53 пар «вопрос → ответ».
            Портрет аудитории сжимает сотню таких записей в несколько абзацев — здесь
            видно, что именно сжимается.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Chip tone="outline">версия корпуса {meta.version}</Chip>
            <Chip tone="outline">{meta.records} записей</Chip>
            <Chip tone="outline">sha256 {meta.sha256.slice(0, 12)}…</Chip>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-stone">
            Только чтение: корпус лежит в git с контрольной суммой, и метрика
            persona_grounding считается по нему. Правка из интерфейса меняла бы заземление
            без коммита — незаметно для всех, кто прогонял раньше.
          </p>
        </section>

        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/portraits/corpus"
            className={`rounded-full border px-3.5 py-1.5 text-sm transition-colors ${
              !source
                ? "border-ink bg-primary text-primary-foreground"
                : "border-hairline text-slate hover:bg-surface"
            }`}
          >
            Все исследования
          </Link>
          {sources.map((s) => (
            <Link
              key={s}
              href={`/portraits/corpus?source=${encodeURIComponent(s)}`}
              className={`rounded-full border px-3.5 py-1.5 text-sm transition-colors ${
                source === s
                  ? "border-ink bg-primary text-primary-foreground"
                  : "border-hairline text-slate hover:bg-surface"
              }`}
            >
              {s.replace(/\.[^.]+$/, "")}
            </Link>
          ))}
        </div>

        <p className="text-sm text-slate">
          {rows.length} записей
          {rows.length > PAGE && ` · показаны первые ${PAGE}`}
        </p>

        <div className="space-y-3">
          {shown.map((s) => (
            <RespondentCard key={s.respondent_id} session={s} />
          ))}
        </div>
      </div>
    </>
  );
}
