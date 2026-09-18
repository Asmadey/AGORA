import Link from "next/link";
import { Activity, MessageCircle, RotateCcw } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { JsonTree } from "@/components/agora/JsonTree";
import { DeleteRunButton } from "@/components/agora/DeleteRunButton";
import { ReportBody } from "@/components/agora/ReportBody";
import { Timeline } from "@/components/agora/Timeline";
import { ShareDialog } from "@/components/agora/ShareDialog";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { loadReport, loadReportPersonas } from "@/lib/server/reports";
import { getTask, taskNumber, loadRunTiming } from "@/lib/server/tasks";
import { notFound } from "next/navigation";
import { resolveRun } from "@/lib/server/run-ref";
import { runSlug } from "@/lib/run-slug";
import { loadTimelineDuration, safePresign } from "@/lib/server/content-pack";
import { DownloadMenu } from "@/components/agora/DownloadMenu";
import { audienceNote } from "@/lib/audience-note";
import { researchTitle } from "@/lib/research-title";
import { parseAnswer, parseReport } from "@/lib/report-view";
import { compareScoreMaps } from "@/lib/rerun";
import { CRITERIA_LABELS, type Criterion } from "@/lib/agora-types";

/**
 * Экран отчёта (PRD §5.E, §6): агрегат и графики сверху, аккордеон по персонам снизу.
 *
 * Порядок блоков отвечает порядку вопросов пользователя: «сколько?» → «почему?» →
 * «кто именно так сказал?». Групповой синтез стоит выше персон, потому что решение
 * принимают по темам, а не по отдельным репликам.
 *
 * Данные читаются из Mongo, куда их кладёт воркер. До задачи #21 экран
 * рендерился из `lib/mock-data`, и это дефект, который не видно на скриншоте:
 * экран с моком и экран с данными отличаются только тем, откуда взялись цифры.
 *
 * Первая страница карточек грузится на сервере вместе с отчётом, остальные —
 * маршрутом `/api/tasks/[id]/report/personas`: при 500 персонах с перекрытием ×3
 * карточки весят два мегабайта, а первый экран показывает пять чисел в шапке.
 */

/** Сколько карточек рисовать сразу. Дальше — догрузка постранично. */
const FIRST_PAGE = 50;

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: slug } = await params;
  const { tenantId, userId } = await requireSession();
  const session = { tenantId, userId };

  // Адрес принимает и номер, и UUID; на UUID отвечает 308 на номер. Наружу
  // отсюда идёт ТОЛЬКО идентификатор: маршруты API работают по нему, и подмена
  // номером дала бы 404 из середины уже открытой страницы.
  const run = await resolveRun(slug, tenantId);
  if (!run) notFound();
  const id = run.id;
  // Свои ссылки страница строит по номеру: иначе переход «Прогресс» → «К
  // отчёту» гонял бы браузер через перенаправление туда и обратно.
  //
  // Объявлено ЗДЕСЬ, а не ниже у прочих производных значений: первая ссылка
  // стоит в раннем возврате «отчёт ещё не готов», и объявление после него
  // давало бы ReferenceError ровно на том экране, который показывают, когда
  // что-то пошло не так.
  const ref = run.seqNo !== null ? runSlug(run.seqNo) : id;

  const envelope = await loadReport(session, id);

  // Отчёта нет — это не ошибка, а «ещё не готов» либо чужой прогон. Различать
  // их на экране нельзя: сообщение «прогон принадлежит другой команде»
  // подтверждает, что такой прогон существует.
  if (!envelope) {
    return (
      <div className="p-8">
        <p className="text-slate">
          Отчёт по этому прогону недоступен: он ещё не готов или принадлежит другой команде.{" "}
          <Link href={`/runs/${ref}/progress`} className="underline underline-offset-4">
            Смотреть прогресс
          </Link>
        </p>
      </div>
    );
  }

  const view = parseReport(envelope.report);
  const [{ items }, timing, task, videoDurationSec] = await Promise.all([
    loadReportPersonas(session, id, { limit: FIRST_PAGE }),
    withTenant(tenantId, (client) => loadRunTiming(client, id)),
    withTenant(tenantId, (client) => getTask(client, id)),
    loadTimelineDuration(session, id),
  ]);
  const parentEnvelope = task?.parentTaskId
    ? await loadReport(session, task.parentTaskId)
    : null;
  const parentView = parentEnvelope ? parseReport(parentEnvelope.report) : null;
  const scoreChanges = parentView
    ? compareScoreMaps(view.scores, parentView.scores)
    : [];
  const answers = items.map(parseAnswer);
  // Номер — для человека, идентификатор — для ссылки. Заголовок «Исследование
  // e81feb92-97a2-43ad-8112-de7503699c60» нельзя ни произнести, ни запомнить, а
  // сослаться на прогон в разговоре нужно каждый день.
  // Ценностей аудитории страница больше не считает: плитку заняли ответы на
  // вопрос 8 анкеты (решение владельца 17.09.2026), а они приходят в отчёте.
  // Запрос к набору персон ради плитки, которой нет, — это лишний поход в базу
  // на каждом открытии отчёта. `valueDistribution` остаётся: ценности аудитории
  // — свойство набора, и они нужны её реестру.
  const number = taskNumber(run.seqNo);
  // Подпись живёт час: записанная в базу ссылка протухла бы к первому открытию.
  const videoUrl = task?.videoRef ? safePresign(task.videoRef) : null;
  // Происхождение числа (конструктор связей, вариант 1) переехало внутрь
  // ReportBody: оно нужно обеим страницам, а собиралось только здесь.

  const qaNote = audienceNote({
    shown: items.length,
    surviving: envelope.audienceSize,
    excludedByQa: view.excludedByQa,
  });

  return (
    <>
      <PageHeader
        // Заголовок остаётся номером: владелец просил ОДИН порядковый
        // идентификатор и назвал его сам — «№ 0050». Название исследования
        // стоит подписью, а не вместо номера: по номеру на прогон ссылаются в
        // разговоре, а название человек меняет, и меняющийся заголовок сделал
        // бы ссылку «посмотри 0050» непроверяемой.
        title={number ? `Исследование ${number}` : `Исследование ${id}`}
        subtitle={
          `${researchTitle(task ?? {})} · ` +
          `${envelope.audienceSize} ответов` +
          (view.replicationCount > 1 ? ` · перекрытие ×${view.replicationCount}` : "") +
          (view.excludedByQa > 0 ? ` · ${view.excludedByQa} исключено QA` : "")
        }
        actions={
          <>
            {/*
              Прогресс доступен и после конца прогона: там видно, сколько занял
              каждый шаг. Раньше на эту страницу попадали только пока считается,
              то есть ровно тогда, когда сравнивать не с чем.
            */}
            <Link
              href={`/runs/${ref}/progress`}
              className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
            >
              <Activity className="h-4 w-4" />
              Прогресс
            </Link>
            {/* Скачивание — сразу за «Прогрессом». Прежде три ссылки лежали
                секцией в середине отчёта, между деревом JSON и метриками: тот,
                кто пришёл забрать расшифровку, искал её в шапке и листал отчёт
                целиком. */}
            <DownloadMenu runId={id} videoUrl={videoUrl} />
            <Link
              href={`/runs/${ref}/chat`}
              className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
            >
              <MessageCircle className="h-4 w-4" />
              Обсудить результаты
            </Link>
            <Link
              href={`/studies/new?rerun=${id}`}
              className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
            >
              <RotateCcw className="h-4 w-4" />
              Перезапустить
            </Link>
            <ShareDialog runId={id} />
            {/* Удаление стоит последним и красное: оно уносит отчёт, за который
                заплачено моделью, и отменить его нечем. Подтверждение — внутри
                кнопки, диалог здесь тяжелее задачи. */}
            <DeleteRunButton runId={id} variant="danger" />
          </>
        }
      />

      {task?.parentTaskId && (
        <section className="mx-8 mt-6 rounded-lg border border-hairline bg-card p-6" aria-labelledby="parent-comparison">
          <h2 id="parent-comparison" className="text-sm font-semibold">
            Сравнение с родительским прогоном
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-slate">
            Этот прогон связан с родителем явно. Ниже показано, что изменилось,
            а не только текущий результат — так разницу можно объяснить выбранным
            режимом памяти и новыми вопросами.
          </p>
          {parentView ? (
            <>
              <Link
                href={`/runs/${task.parentTaskId}`}
                className="mt-3 inline-block text-xs underline underline-offset-4"
              >
                Открыть родительский прогон
              </Link>
              {scoreChanges.length === 0 ? (
                <p className="mt-3 text-sm">Баллы базовых критериев не изменились.</p>
              ) : (
                <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
                  {scoreChanges.map((change) => (
                    <div key={change.key} className="rounded-md border border-hairline p-3">
                      <dt className="text-slate">
                        {CRITERIA_LABELS[change.key as Criterion] ?? change.key}
                      </dt>
                      <dd className="mt-1">
                        {change.parent ?? "нет данных"} → {change.current ?? "нет данных"}
                        {change.delta !== null && (
                          <span className="ml-2 text-xs text-slate">
                            ({change.delta > 0 ? "+" : ""}{change.delta.toFixed(2)})
                          </span>
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </>
          ) : (
            <p className="mt-3 text-sm text-slate">
              Отчёт родительского прогона недоступен, поэтому сравнение пока не построено.
            </p>
          )}
        </section>
      )}

        <ReportBody
          view={view}
          answers={answers}
          audienceSize={envelope.audienceSize}
          runId={id}
          qaNote={qaNote}
          scope="full"
          videoDurationSec={videoDurationSec}
          timeline={<Timeline runId={id} processingSec={timing?.totalSec ?? null} />}
          rawReport={
            /*
              Отчёт в исходном виде (п. 20).

              Экран показывает выжимку — числа, вербатимы, точки риска. Всё
              остальное лежит в отчёте и доставалось только скачиванием файла.
              Дерево отвечает на вопрос «а что там ещё есть» на месте.

              Свёрнуто по умолчанию: это инструмент для разбора, а не часть
              чтения отчёта, и раскрытым оно оттесняло бы выводы вниз.

              Наружу по публичной ссылке НЕ идёт: там оно означало бы выгрузку
              отчёта целиком в машиночитаемом виде, о чём никто не просил.
            */
            <details className="rounded-lg border border-hairline bg-card p-6">
              <summary className="cursor-pointer text-sm font-semibold">
                Отчёт в исходном виде
              </summary>
              <div className="mt-3">
                <JsonTree value={envelope.report as never} label="отчёт" />
              </div>
            </details>
          }
        />
    </>
  );
}
