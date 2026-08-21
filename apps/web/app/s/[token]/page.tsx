import { notFound } from "next/navigation";

import { withShareToken } from "@/lib/server/db";
import { loadReport } from "@/lib/server/reports";
import { parseReport } from "@/lib/report-view";
import { Chip, ScoreBar, StatCard } from "@/components/agora/Primitives";
import { CRITERIA, CRITERIA_LABELS } from "@/lib/agora-types";

/**
 * Отчёт по публичной ссылке (#29) — без входа в систему.
 *
 * ─── Что здесь ограничивает доступ ────────────────────────────────────────
 * Не сессия, а токен из адреса. Соединение идёт под ролью `agora_share`,
 * которой политики (03_rls.sql) отдают ровно один отчёт — тот, на который
 * выпущена ссылка, — и только пока она не отозвана и не просрочена. Ошибка в
 * этом файле не может показать чужой отчёт: показывать нечего, база вернёт
 * пустоту.
 *
 * ─── Почему страница скупее внутренней ────────────────────────────────────
 * Ссылка уходит наружу. Показываем то, ради чего ей делятся: числа, темы и
 * выводы. Персональных карточек, таймлайна с материалом и сырого JSON здесь
 * нет — при `scope = 'aggregate'` их не показывает и политика.
 *
 * ─── Почему «ссылка недействительна» вместо «отчёт не найден» ─────────────
 * Разные ответы на «токена нет» и «токен просрочен» сообщали бы владельцу
 * ссылки, существовала ли она когда-нибудь. Ответ один.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function SharedReportPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  // Токен проверяет БАЗА, а не этот файл: политика сверяет
  // app.current_share_token_hash(), срок и отзыв. Отсюда мы узнаём только, какой
  // прогон какого арендатора ссылка открывает.
  const grant = await withShareToken(token, async (client) => {
    const { rows } = await client.query<{
      id: string;
      tenant_id: string;
      task_id: string | null;
      scope: string;
    }>(
      `SELECT id, tenant_id, task_id, scope
         FROM report_shares
        WHERE token_hash = app.current_share_token_hash()
          AND revoked_at IS NULL
          AND (expires_at IS NULL OR expires_at > now())`,
    );
    if (!rows[0]?.task_id) return null;

    // Просмотр записывается: владелец ссылки вправе знать, что ею
    // воспользовались. IP и агент не собираем — колонки для них есть, но
    // заполнять их без явного решения не станем.
    await client.query(
      "INSERT INTO report_share_views (tenant_id, share_id) VALUES ($1, $2)",
      [rows[0].tenant_id, rows[0].id],
    );
    return rows[0];
  }).catch(() => null);

  if (!grant?.task_id) notFound();

  // Отчёт лежит в MongoDB (#21). RLS туда не достаёт, поэтому фильтр по
  // арендатору обязателен — и берётся он из строки ссылки, а не из адреса.
  const envelope = await loadReport(
    { tenantId: grant.tenant_id, userId: "" },
    grant.task_id,
  );
  const row = envelope ? { scope: grant.scope, report: envelope.report, title: null } : null;

  if (!row) notFound();

  const view = parseReport(row.report);
  const fmt = (v: number | null, digits = 1) => (v === null ? "—" : v.toFixed(digits));

  return (
    <div className="mx-auto max-w-4xl space-y-8 p-8">
      <header>
        <p className="text-xs uppercase tracking-wide text-slate">Отчёт исследования</p>
        <h1 className="mt-1 text-2xl font-semibold">{row.title || "Синтетическая фокус-группа"}</h1>
        <p className="mt-2 text-sm text-slate">
          Открыто по публичной ссылке. Данные не обновляются: это снимок на момент прогона.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Общее впечатление" value={fmt(view.scores.overall_impression)} hint="из 10" />
        <StatCard label="NPS" value={fmt(view.nps, 0)} hint="промоутеры минус критики" />
        <StatCard
          label="Досмотрят до конца"
          value={view.retentionRate === null ? "—" : `${view.retentionRate.toFixed(0)}%`}
        />
        <StatCard label="Эмоц. индекс" value={fmt(view.emotionalIndex)} hint="из 10" />
      </section>

      <section className="rounded-lg border border-hairline bg-card p-6">
        <h2 className="text-sm font-semibold">Оценки по критериям</h2>
        <div className="mt-4 space-y-3">
          {CRITERIA.map((c) => (
            <ScoreBar key={c} label={CRITERIA_LABELS[c]} value={view.scores[c] ?? 0} />
          ))}
        </div>
      </section>

      {view.narrative.length > 0 && (
        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Выводы</h2>
          <ul className="mt-3 space-y-2 text-sm leading-relaxed">
            {view.narrative.map((line) => (
              <li key={line}>— {line}</li>
            ))}
          </ul>
        </section>
      )}

      {row.scope === "full" && view.themes.length > 0 && (
        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Темы</h2>
          <div className="mt-3 space-y-4">
            {view.themes.map((theme) => (
              <div key={theme.title}>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{theme.title}</span>
                  {theme.agreement && <Chip>{theme.agreement}</Chip>}
                </div>
                {theme.summary && (
                  <p className="mt-1 text-sm leading-relaxed text-foreground/80">{theme.summary}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <footer className="border-t border-hairline pt-4 text-xs leading-relaxed text-slate">
        <p>
          Выборка: {view.sampleSize} ответов
          {view.excludedByQa > 0 && `, ${view.excludedByQa} исключено проверкой качества`}
          {view.replicationCount > 1 && `, перекрытие ×${view.replicationCount}`}.
        </p>
        {view.disclaimer && <p className="mt-2">{view.disclaimer}</p>}
      </footer>
    </div>
  );
}
