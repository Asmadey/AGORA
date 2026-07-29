import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";

/**
 * Портреты аудиторий (задача #24). Витрина: список портретов + источник.
 * Редактор .md и авто-дистилляция из датасета подключаются вместе с бэкендом.
 */

const PORTRAITS = [
  {
    name: "Ядро сериальной аудитории 25–44",
    source: "distilled" as const,
    updated: "26.07.2026",
    excerpt:
      "Смотрит вечером, часто фоном. Решение продолжать принимает по героям, а не по сюжету. Болезненно реагирует на неубедительные мотивации — это главная причина отвала.",
  },
  {
    name: "Зрители 45+, региональные центры",
    source: "distilled" as const,
    updated: "26.07.2026",
    excerpt:
      "Высокая толерантность к медленному темпу, низкая — к жестокости. Досматривает до конца, если материал не нарушил личную границу допустимого.",
  },
  {
    name: "Молодая аудитория промо-роликов",
    source: "manual" as const,
    updated: "24.07.2026",
    excerpt:
      "Решение смотреть принимает за первые секунды. Крайне чувствительна к темпу, лояльна к знакомым вселенным, ориентируется на соцсети.",
  },
];

const SOURCE_LABEL = {
  manual: "написан вручную",
  distilled: "дистилляция из корпуса",
  context_file: "из файла контекста",
};

export default function PortraitsPage() {
  return (
    <>
      <PageHeader
        title="Портреты аудиторий"
        subtitle="Описания сегментов, которые подмешиваются в генерацию персон. Портрет уточняет персон, но не переопределяет заземление на корпус."
        actions={
          <button className="rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary">
            Новый портрет
          </button>
        }
      />

      <div className="grid gap-3 p-8 lg:grid-cols-2">
        {PORTRAITS.map((p) => (
          <article
            key={p.name}
            className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5 transition-colors hover:border-muted-foreground/40"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-medium">{p.name}</h2>
              <Chip tone="outline">{SOURCE_LABEL[p.source]}</Chip>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{p.excerpt}</p>
            <p className="mt-4 text-xs text-muted-foreground">Обновлён {p.updated}</p>
          </article>
        ))}
      </div>
    </>
  );
}
