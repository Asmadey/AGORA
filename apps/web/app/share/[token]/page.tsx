import { withShareToken } from "@/lib/server/db";
import { loadReport, loadReportPersonas } from "@/lib/server/reports";
import { parseAnswer, parseReport } from "@/lib/report-view";
import { ReportBody } from "@/components/agora/ReportBody";
import { Timeline } from "@/components/agora/Timeline";
import { audienceNote } from "@/lib/audience-note";
import { researchTitle } from "@/lib/research-title";
import { classifyShareState, type ShareLinkState } from "@/lib/share";
import { parseScope } from "@/lib/share-scope";
import { loadTimelineDuration } from "@/lib/server/content-pack";
import { notFound } from "next/navigation";

/**
 * Отчёт по публичной ссылке (#29) — без входа в систему.
 *
 * ─── Что здесь ограничивает доступ ────────────────────────────────────────
 * Не сессия, а токен из адреса. Соединение идёт под ролью `agora_share`,
 * которой политики (03_rls.sql, миграция 39) отдают ровно один прогон — тот,
 * на который выпущена ссылка, — и только пока она не отозвана и не просрочена.
 * Ошибка в этом файле не может показать чужой отчёт: показывать нечего, база
 * вернёт пустоту.
 *
 * ─── Почему страница больше не рисует отчёт сама ──────────────────────────
 * Рисовала — и это был дефект, о котором сообщил владелец. Здесь от руки
 * повторялись пять секций внутреннего отчёта из двенадцати, а выбор «весь
 * отчёт / только сводка» управлял ровно одной из них. Поэтому оба режима
 * показывали сводку.
 *
 * Дописать недостающие семь значило бы завести расхождение заново: две
 * реализации одного экрана расходятся молча, потому что рядом их никто не
 * держит. Теперь тело рисует общий `ReportBody`, а область решает
 * `lib/share-scope`.
 *
 * ─── Почему просроченная ссылка получает 410, а неизвестная 404 ───────────
 * Токен содержит 32 случайных байта, поэтому держатель настоящего адреса уже
 * знает, что ссылка существовала. 410 помогает ему понять, что нужно попросить
 * новую ссылку, а 404 не подтверждает существование подобранного адреса.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Сколько карточек персон рисовать сразу — как на внутренней странице. */
const FIRST_PAGE = 50;

/**
 * Единственный ответ на «токена нет», «ссылка отозвана» и «срок вышел».
 *
 * Своя страница, а не `notFound()`: в потоковой отрисовке статус успевает
 * уехать до вызова, и общий 404 приходит с кодом 200 — то есть выглядит как
 * успешный ответ с чужой страницей внутри. Явный экран честнее: он говорит про
 * ссылку, а не про несуществующий адрес.
 */
function Invalid({ state }: { state: Exclude<ShareLinkState, "active" | "missing"> }) {
  const revoked = state === "revoked";
  return (
    <div className="mx-auto max-w-md p-16 text-center">
      <h1 className="text-lg font-semibold">
        {revoked ? "Ссылка отозвана" : "Срок ссылки истёк"}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-slate">
        {revoked
          ? "Владелец исследования закрыл эту ссылку. Попросите выпустить новую."
          : "Срок действия этой ссылки закончился. Попросите владельца выпустить новую."}
      </p>
    </div>
  );
}

export default async function SharedReportPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  // Токен проверяет БАЗА, а не этот файл: политика сверяет
  // app.current_share_token_hash(), срок и отзыв. Отсюда мы узнаём только, какой
  // прогон какого арендатора ссылка открывает и что именно показывать.
  const grant = await withShareToken(token, async (client) => {
    const { rows } = await client.query<{
      id: string;
      tenant_id: string;
      task_id: string | null;
      scope: string;
      revoked_at: Date | null;
      expires_at: Date | null;
    }>(
      `SELECT id, tenant_id, task_id, scope, revoked_at, expires_at
         FROM report_shares
        WHERE token_hash = app.current_share_token_hash()`,
    );
    const row = rows[0];
    if (!row) return null;

    const state = classifyShareState(
      { revokedAt: row.revoked_at, expiresAt: row.expires_at },
    );
    if (state === "expired" || state === "revoked") return { state };
    if (!row.task_id) return { state: "missing" as const };

    // Просмотр записывается: владелец ссылки вправе знать, что ею
    // воспользовались. IP и агент не собираем — колонки для них есть, но
    // заполнять их без явного решения не станем.
    await client.query(
      "INSERT INTO report_share_views (tenant_id, share_id) VALUES ($1, $2)",
      [row.tenant_id, row.id],
    );

    // Название прогона. До миграции 39 роль `agora_share` не имела доступа к
    // `tasks` вовсе, и страница подставляла заглушку — не потому, что название
    // не хранится, а потому, что прочитать его было нечем.
    const { rows: taskRows } = await client.query<{ title: string | null; source_name: string | null }>(
      "SELECT title, source_name FROM tasks WHERE id = $1",
      [row.task_id],
    );

    return { ...row, state, task: taskRows[0] ?? null };
  }).catch(() => null);

  // `notFound` даёт подобранному токену настоящий HTTP 404. Рендер страницы не
  // умеет выдать свой 410, поэтому обработчик таймлайна только для чтения возвращает
  // 410 для того же состояния, когда видит истёкшую или отозванную строку.
  if (!grant) notFound();
  if (grant.state === "missing") notFound();
  if (grant.state !== "active") return <Invalid state={grant.state} />;
  if (!grant.task_id) notFound();

  // Отчёт лежит в MongoDB (#21). RLS туда не достаёт, поэтому фильтр по
  // арендатору обязателен — и берётся он из строки ссылки, а не из адреса.
  const session = { tenantId: grant.tenant_id, userId: "" };
  const envelope = await loadReport(session, grant.task_id);
  if (!envelope) notFound();

  const scope = parseScope(grant.scope);
  const view = parseReport(envelope.report);

  const videoDurationSec =
    scope === "full" ? await loadTimelineDuration(session, grant.task_id) : null;

  // Карточки персон нужны и как содержимое секции, и как основание раскрытия
  // под метриками. В режиме «только сводка» ни то, ни другое не показывается,
  // поэтому и читать их незачем: лишняя выборка на мегабайты ради данных,
  // которые не попадут на страницу.
  const answers =
    scope === "full"
      ? (await loadReportPersonas(session, grant.task_id, { limit: FIRST_PAGE })).items.map(parseAnswer)
      : [];

  const qaNote =
    scope === "full"
      ? audienceNote({
          shown: answers.length,
          surviving: envelope.audienceSize,
          excludedByQa: view.excludedByQa,
        })
      : null;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="px-8 pt-10">
        <p className="text-xs uppercase tracking-wide text-slate">Отчёт исследования</p>
        <h1 className="mt-1 text-2xl font-semibold">
          {researchTitle(grant.task ?? {})}
        </h1>
        <p className="mt-2 text-sm text-slate">
          Открыто по публичной ссылке. Данные не обновляются: это снимок на момент прогона.
          {scope === "aggregate" && " Показана сводка — без ответов персон и материала."}
        </p>
      </header>

      {/*
        Кнопок действий здесь нет и быть не может: «Поделиться», «Скачать»,
        «Перезапустить», «Удалить» и чат ведут в разделы, закрытые сессией.
        Гостю они предлагали бы то, чего он не может сделать.
      */}
      <ReportBody
        view={view}
        answers={answers}
        audienceSize={envelope.audienceSize}
        runId={grant.task_id}
        qaNote={qaNote}
        scope={scope}
        videoDurationSec={videoDurationSec}
        // Материал берётся маршрутом под токеном: у гостя нет сессии, и
        // внутренний /api/tasks/[id]/timeline ему ответит отказом.
        timeline={<Timeline runId={grant.task_id} src={`/share/${token}/timeline`} />}
      />
    </div>
  );
}
