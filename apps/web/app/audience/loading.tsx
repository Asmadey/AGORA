import { SkeletonGrid, SkeletonHeader } from "@/components/agora/States";

/** Загрузка наборов аудитории: та же сетка плашек, что приедет с данными. */
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
