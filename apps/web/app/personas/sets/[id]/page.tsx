import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { EmptyState } from "@/components/agora/States";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listPersonas, listPersonaSets } from "@/lib/server/personas";
import { snapshotRecordsOfPersonaSet } from "@/lib/server/corpus-db";
import { groundingReport, GROUNDING_PROP_TOL } from "@/lib/persona-grounding";
import { avatarHue, initials } from "@/lib/report-view";

/**
 * Состав одного набора персон.
 *
 * Раньше наборы были подписями над сеткой: имя, размер, seed — и всё. Узнать,
 * кто в наборе, было нельзя ни одним кликом, хотя именно этот вопрос задают
 * перед запуском: «на ком я буду проверять ролик». Реестр `/personas` показывал
 * всех персон арендатора вперемешку, без разделения по наборам, поэтому ответа
 * не было и там.
 *
 * Экран отвечает ровно на него и ничего не добавляет: те же плашки, что в
 * реестре, но только этого набора, плюс его параметры воспроизводимости.
 */

export const dynamic = "force-dynamic";

function generation(age: number): string {
  const year = new Date().getFullYear() - age;
  if (year >= 2013) return "Альфа";
  if (year >= 1997) return "Z";
  if (year >= 1981) return "Y";
  if (year >= 1965) return "X";
  return "Бумеры";
}

export default async function PersonaSetPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { tenantId } = await requireSession();

  const { set, personas, records } = await withTenant(tenantId, async (client) => {
    const sets = await listPersonaSets(client, id);
    return {
      set: sets[0] ?? null,
      personas: await listPersonas(client, id),
      records: await snapshotRecordsOfPersonaSet(client, id),
    };
  });

  // 404, а не пустая страница: чужой набор под RLS не находится, и это тот же
  // ответ, что на несуществующий идентификатор.
  if (!set) notFound();

  const incomplete = set.personaCount < set.size;

  /*
    Заземление считается по СЛЕПКУ, с которого собран набор, а не по датасету на
    сегодня: датасет правят, и сравнение с его текущей версией отвечало бы на
    другой вопрос — «похож ли старый набор на новые данные».
  */
  const grounding = groundingReport(personas, records);

  return (
    <>
      <PageHeader
        title={set.name}
        subtitle={`Набор из ${set.personaCount} персон${
          set.seed !== null ? ` · seed ${set.seed}` : ""
        } · создан ${new Date(set.createdAt).toLocaleDateString("ru-RU")}`}
        actions={
          <Link
            href="/personas"
            className="inline-flex items-center gap-2 rounded-full border border-hairline px-4 py-2 text-sm transition-colors hover:bg-surface"
          >
            <ArrowLeft className="h-4 w-4" />
            К реестру
          </Link>
        }
      />

      <div className="space-y-6 p-8">
        {/*
          Метрика persona_grounding жила только в отчёте гейта — там, куда
          владелец продукта не заходит. Вопрос «похожа ли собранная аудитория на
          датасет» задают, глядя на набор, и отвечать на него приходилось на
          слово.
        */}
        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Заземление на датасет</h2>
          {!grounding.comparable ? (
            <p className="mt-2 text-xs leading-relaxed text-slate">
              Сравнивать не с чем: слепок датасета пуст либо набор ещё собирается.
              Это «не проверено», а не «всё в порядке».
            </p>
          ) : grounding.deviations.length === 0 ? (
            <p className="mt-2 text-xs leading-relaxed text-slate">
              Доли возраста, типа населённого пункта и пола совпадают с датасетом
              в пределах {Math.round(GROUNDING_PROP_TOL * 100)} процентных пунктов.
            </p>
          ) : (
            <>
              <p className="mt-2 text-xs leading-relaxed text-slate">
                Доли разошлись с датасетом больше чем на{" "}
                {Math.round(GROUNDING_PROP_TOL * 100)} процентных пунктов. Само по
                себе это не дефект — набор меньше корпуса, и округление на
                маленьком наборе даёт перекос. Но выводы по перекошенному срезу
                относятся к нему, а не к аудитории.
              </p>
              <dl className="mt-3 space-y-1 text-xs">
                {grounding.deviations.map((d) => (
                  <div key={`${d.dimension}-${d.bucket}`} className="flex items-baseline gap-2">
                    <dt className="text-slate">
                      {d.dimension} · {d.bucket}
                    </dt>
                    <dd className="tabular-nums">
                      набор {Math.round(d.generated * 100)}% против{" "}
                      {Math.round(d.real * 100)}% в датасете
                    </dd>
                  </div>
                ))}
              </dl>
            </>
          )}
        </section>

        {incomplete && (
          <p className="rounded-lg border border-warning/30 bg-warning-soft/60 p-4 text-sm leading-relaxed">
            В наборе {set.personaCount} персон из заказанных {set.size}: генерация
            оборвалась или была остановлена. Прогон на таком наборе пройдёт, но
            распределения по сегментам будут смещены относительно заданных критериев.
          </p>
        )}

        {/* Критерии генерации показываются как есть, а не пересказом: по ним
            набор воспроизводится, и переписывание их своими словами — лишний
            повод разойтись с тем, что реально ушло в генератор. */}
        {Object.keys(set.generationConfig ?? {}).length > 0 && (
          <section className="rounded-xl border border-hairline bg-card p-5">
            <h2 className="text-sm font-semibold">Критерии генерации</h2>
            <p className="mt-1 text-xs text-slate">
              Тот же набор с тем же seed воспроизводится по этим параметрам
            </p>
            <dl className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2">
              {Object.entries(set.generationConfig).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-3 text-sm">
                  <dt className="text-slate">{key}</dt>
                  <dd className="text-right">
                    {Array.isArray(value) ? value.join(", ") : String(value ?? "—")}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {personas.length === 0 ? (
          <EmptyState
            title="В наборе нет персон"
            description="Набор создан, но генерация не сохранила ни одной персоны. Такой набор нельзя использовать для прогона — соберите аудиторию заново."
            action={{ href: "/studies/new", label: "Собрать аудиторию" }}
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {personas.map((p) => {
              const dna = p.dna as unknown as Record<string, Record<string, unknown>>;
              const age = Number(dna?.demographics?.age ?? 0);
              const city = String(dna?.demographics?.city ?? "");
              const hue = avatarHue(p.id);
              return (
                <Link
                  key={p.id}
                  href={`/personas/${p.id}`}
                  className="rounded-xl border border-hairline bg-card p-5 transition-colors hover:border-hairline-strong"
                >
                  <div className="flex items-start gap-3">
                    <div
                      className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-sm font-semibold"
                      style={{
                        backgroundColor: `hsl(${hue} 70% 92%)`,
                        color: `hsl(${hue} 45% 32%)`,
                      }}
                    >
                      {initials(p.name)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate font-medium">{p.name}</h3>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {age > 0 && <Chip>{generation(age)}</Chip>}
                        {age > 0 && <Chip tone="outline">{age} лет</Chip>}
                        {city && <Chip tone="outline">{city}</Chip>}
                      </div>
                    </div>
                  </div>
                  {p.narrative && (
                    <p className="mt-4 line-clamp-2 text-sm leading-relaxed text-slate">
                      {p.narrative}
                    </p>
                  )}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
