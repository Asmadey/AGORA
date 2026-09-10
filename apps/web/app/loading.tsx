import { SkeletonHeader, SkeletonList } from "@/components/agora/States";

/**
 * Запасной скелетон: показывается разделу, у которого нет своего.
 *
 * Намеренно без формы конкретного экрана. Раньше здесь стоял список прогонов —
 * файл писался, когда список жил на корне, — и после его переезда на
 * `/researches` четыре высокие карточки рисовались на всех разделах подряд,
 * включая те, где ничего похожего нет.
 *
 * Форма экрана принадлежит экрану: раздел, который ждёт данные, заводит
 * собственный `loading.tsx`. Это держит `lib/first-paint.test.ts`.
 */
export default function Loading() {
  return (
    <>
      <SkeletonHeader />
      <div className="p-8">
        <SkeletonList rows={3} height="h-16" />
      </div>
    </>
  );
}
