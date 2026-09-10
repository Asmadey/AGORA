import { Skeleton, SkeletonHeader, SkeletonList } from "@/components/agora/States";

/**
 * Загрузка паспорта корпуса.
 *
 * Сверху абзац описания, ниже — записи корпуса. Порядок повторяет экран:
 * если поставить список первым, готовая страница сдвинет его вниз ровно
 * тогда, когда пользователь начал его читать.
 */
export default function Loading() {
  return (
    <>
      <SkeletonHeader />
      <div className="space-y-6 p-8">
        <div className="max-w-2xl space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
        </div>
        <SkeletonList rows={4} height="h-16" />
      </div>
    </>
  );
}
