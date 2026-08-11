import { SkeletonGrid, SkeletonHeader } from "@/components/agora/States";

/** Загрузка портретов аудитории. */
export default function Loading() {
  return (
    <>
      <SkeletonHeader />
      <div className="p-8">
        <SkeletonGrid cards={6} />
      </div>
    </>
  );
}
