import Link from "next/link";
import { ArrowLeft, BarChart3, MessageCircle, User } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { EmptyState } from "@/components/agora/States";

/**
 * Чат по результатам исследования — задача #28, ещё не реализована.
 *
 * До этого здесь стоял работающий на вид чат: два режима, переписка-затравка с
 * подробным разбором сегмента 45+ и таймкодами. Всё это было написано руками в
 * файле. Функция `send` не обращалась ни к какому маршруту — она добавляла в
 * ленту заранее заготовленную строку, одну на любой вопрос.
 *
 * Такой экран хуже отсутствующего. Пользователь задаёт вопрос про своё
 * исследование, получает связный ответ с цитатами и таймкодами — и у него нет
 * ни одного способа узнать, что ответ относится к выдуманному прогону. Дефект
 * проявится тогда, когда по этому ответу примут решение.
 *
 * Поэтому экран честно говорит, чего пока нет. Сам маршрут оставлен: на него
 * ведут ссылки из отчёта и из карточки персоны, и удалять их ради заглушки
 * значило бы прятать запланированную функцию.
 *
 * Что здесь будет по #28 — два разных собеседника, а не одна фича с
 * переключателем: «Аналитик» видит весь срез и отвечает по агрегату, «Персона»
 * видит только свой профиль, видео и свои прежние ответы — та же структурная
 * изоляция, что в основном конвейере. Ответ без таймкода или цитаты ответом не
 * считается.
 */

export default async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <>
      <PageHeader
        title="Обсудить результаты"
        subtitle="Вопросы к аналитику по всему исследованию и к отдельной персоне по её ответам."
        actions={
          <Link
            href={`/runs/${id}`}
            className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
          >
            <ArrowLeft className="h-4 w-4" />
            К отчёту
          </Link>
        }
      />

      <div className="space-y-6 p-8">
        <EmptyState
          icon={<MessageCircle className="h-5 w-5" />}
          title="Чат по результатам ещё не подключён"
          description="Это задача #28, она идёт после сквозной верификации конвейера. Пока отвечать на вопросы нечем: экран не должен показывать ответы, которых модель не давала."
          action={{ href: `/runs/${id}`, label: "Вернуться к отчёту" }}
        />

        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Что здесь появится</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="flex gap-3">
              <BarChart3 className="mt-0.5 h-4 w-4 shrink-0 text-slate" />
              <div>
                <p className="text-sm font-medium">Аналитик</p>
                <p className="mt-1 text-sm leading-relaxed text-slate">
                  Видит весь срез и отвечает по агрегату. Каждое утверждение — со
                  ссылкой на таймкод или цитату персоны; без опоры ответ не выдаётся.
                </p>
              </div>
            </div>
            <div className="flex gap-3">
              <User className="mt-0.5 h-4 w-4 shrink-0 text-slate" />
              <div>
                <p className="text-sm font-medium">Допрос персоны</p>
                <p className="mt-1 text-sm leading-relaxed text-slate">
                  Видит только свой профиль, видео и свои прежние ответы — та же
                  изоляция, что в основном конвейере. Чужих ответов персона не знает.
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
