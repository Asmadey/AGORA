import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { notFound } from "next/navigation";

import { PageHeader } from "@/components/AppShell";
import { ChatView } from "@/components/agora/ChatView";
import { EmptyState } from "@/components/agora/States";
import { requireSession } from "@/lib/server/guard";
import { resolveRun } from "@/lib/server/run-ref";
import { withTenant } from "@/lib/server/db";
import { getTask } from "@/lib/server/tasks";
import { researchTitle } from "@/lib/research-title";
import { MessageCircle } from "lucide-react";

/**
 * Чат по результатам исследования — задача #28.
 *
 * ─── Что здесь было раньше ────────────────────────────────────────────────
 * Сначала чат, работавший НА ВИД: функция отправки возвращала заготовленную
 * строку, ни к какому маршруту не обращаясь. Потом — честная заглушка,
 * говорившая, что функции нет. Заглушка была лучше: пользователь, получивший
 * связный ответ с цитатами по выдуманному прогону, не имел способа отличить
 * его от настоящего, и дефект проявился бы тогда, когда по ответу примут
 * решение.
 *
 * ─── Два собеседника, а не один с переключателем ──────────────────────────
 * «Аналитик» видит весь срез и отвечает по агрегату. «Персона» видит только
 * свой профиль, материал и СВОИ прежние ответы — та же структурная изоляция,
 * что в конвейере, и та же проверка, что в #18.
 *
 * ─── Почему чат живёт только поверх завершённого прогона ──────────────────
 * Спрашивать про отчёт, которого ещё нет, значит получать ответ по пустому
 * срезу — правдоподобный и ни на чём не основанный.
 */

export const dynamic = "force-dynamic";

export default async function ChatPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ persona?: string }>;
}) {
  const { id: slug } = await params;
  const { persona } = await searchParams;
  const { tenantId, userId } = await requireSession();

  const run = await resolveRun(slug, tenantId, "/chat");
  if (!run) notFound();
  const id = run.id;

  const task = await withTenant(tenantId, (client) => getTask(client, id));
  const ready = task?.status === "REPORT_READY";

  // Имя персоны — чтобы в ленте стояло «Анна», а не «Персона». В режиме
  // аналитика запрос не делается вовсе.
  const personaName = persona
    ? await withTenant(tenantId, async (client) => {
        const { rows } = await client.query<{ name: string }>(
          "SELECT name FROM personas WHERE id = $1::uuid",
          [persona],
        );
        return rows[0]?.name ?? null;
      })
    : null;

  return (
    <>
      <PageHeader
        title="Обсудить результаты"
        subtitle={
          persona
            ? `Допрос персоны${personaName ? `: ${personaName}` : ""} · ${researchTitle(task ?? {})}`
            : `Аналитик по всему исследованию · ${researchTitle(task ?? {})}`
        }
        back={
          <Link
            href={`/runs/${id}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-hairline px-2.5 py-1.5 text-sm transition-colors hover:bg-secondary"
          >
            <ArrowLeft className="h-4 w-4" />
            К отчёту
          </Link>
        }
      />

      <div className="p-8">
        {!ready ? (
          <EmptyState
            icon={<MessageCircle className="h-5 w-5" />}
            title="Исследование ещё не завершено"
            description="Чат работает поверх готового отчёта: пока прогон идёт, обсуждать нечего — ответ собрался бы по пустому срезу и выглядел бы настоящим."
            action={{ href: `/runs/${id}/progress`, label: "Смотреть прогресс" }}
          />
        ) : (
          <ChatView
            runId={id}
            mode={persona ? "persona" : "analyst"}
            personaId={persona}
            personaName={personaName ?? undefined}
          />
        )}
      </div>
    </>
  );
}
