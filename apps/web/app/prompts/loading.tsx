import { SkeletonHeader, SkeletonList } from "@/components/agora/States";

/** Загрузка Промпт-студии. */
export default function Loading() {
  return (
    <>
      <SkeletonHeader />
      <div className="p-8">
        <SkeletonList rows={8} height="h-16" />
      </div>
    </>
  );
}
