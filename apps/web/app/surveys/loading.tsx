import { SkeletonHeader, SkeletonList } from "@/components/agora/States";

/** Загрузка списка анкет: строки той же высоты, что и карточки анкет. */
export default function Loading() {
  return (
    <>
      <SkeletonHeader />
      <div className="p-8">
        <SkeletonList rows={4} height="h-24" />
      </div>
    </>
  );
}
