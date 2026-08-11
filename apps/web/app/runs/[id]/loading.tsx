import { Skeleton, SkeletonHeader, SkeletonList } from "@/components/agora/States";

/**
 * Загрузка отчёта.
 *
 * Отчёт открывается дольше остальных экранов: сводка читается из Mongo целиком,
 * а следом первая страница карточек персон. Форма заглушки повторяет порядок
 * блоков отчёта — пять плашек метрик, нарратив, два графика, аккордеон, — чтобы
 * ожидание не превращалось в скачок вёрстки.
 */
export default function Loading() {
  return (
    <>
      <SkeletonHeader />
      <div className="space-y-8 p-8">
        <Skeleton className="h-12 w-full" />

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>

        <Skeleton className="h-36 w-full" />

        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>

        <SkeletonList rows={5} height="h-16" />
      </div>
    </>
  );
}
