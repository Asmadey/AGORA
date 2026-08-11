import { SkeletonHeader, SkeletonList } from "@/components/agora/States";

/**
 * Загрузка списка прогонов.
 *
 * Форма повторяет будущий список: шапка и строки той же высоты. Когда данные
 * приезжают, страница не прыгает — место уже занято. Спиннер по центру дал бы
 * скачок вёрстки ровно в момент, когда пользователь начал читать.
 */
export default function Loading() {
  return (
    <>
      <SkeletonHeader />
      <div className="p-8">
        <SkeletonList rows={4} height="h-28" />
      </div>
    </>
  );
}
