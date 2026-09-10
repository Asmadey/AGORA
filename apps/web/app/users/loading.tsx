import { SkeletonHeader, SkeletonList } from "@/components/agora/States";

/**
 * Загрузка списка участников команды.
 *
 * Строки ниже карточек прогона: участник — это строка с именем, почтой и
 * ролью, а не плашка с содержимым.
 */
export default function Loading() {
  return (
    <>
      <SkeletonHeader />
      <div className="p-8">
        <SkeletonList rows={5} height="h-14" />
      </div>
    </>
  );
}
