import { SkeletonGrid, SkeletonHeader } from "@/components/agora/States";

/** Загрузка реестра персон: сетка плашек той же формы, что и будущая. */
export default function Loading() {
  return (
    <>
      <SkeletonHeader />
      <div className="p-8">
        <SkeletonGrid cards={8} />
      </div>
    </>
  );
}
