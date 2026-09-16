import { valueChartRows } from "@/lib/values-chart";

/**
 * Семнадцать ценностей столбиками — в размер обычной плитки показателей.
 *
 * ─── Почему столбик ПОД текстом, а не рядом ───────────────────────────────
 * Плитка узкая (около 330 px), а названия длинные: «Служение Отечеству и
 * ответственность за его судьбу» — 50 знаков. Подпись слева и столбик справа
 * оставили бы столбику треть ширины, и разница между 18 и 12 перестала бы
 * читаться.
 *
 * Поэтому дорожка занимает всю ширину строки, а подпись и число лежат НА ней.
 * Так у столбика полная ширина, а у подписи — тоже.
 *
 * ─── Почему семнадцать строк помещаются ───────────────────────────────────
 * Строка — 15 px: 11-пиксельный шрифт в 14-пиксельной дорожке плюс просвет.
 * Семнадцать строк дают 255 px, что укладывается в высоту соседних плиток с
 * их тремя-четырьмя абзацами обоснования.
 */
export function ValuesChart({ counts }: { counts: Record<string, number> }) {
  const rows = valueChartRows(counts);

  /*
    Оболочка повторяет `StatCard` по классам, но карточкой не является:
    у `StatCard` значение — строка в крупном начертании, и график туда не
    ложится. Переделывать `value` в `ReactNode` ради одной плитки значило бы
    разрешить крупному числу быть чем угодно во всех остальных.
  */
  return (
    <div className="rounded-lg border border-hairline bg-card p-4">
      {/*
        Оговорка стоит В СТРОКЕ заголовка, а не подвалом под графиком.

        Подвал владелец просил убрать — плитка должна быть в высоту соседних.
        Но убрать оговорку совсем нельзя: «Ценности ВЦИОМ» — это название
        ПЕРЕЧНЯ, а числа принадлежат синтетической аудитории. Без пояснения
        плитка читается как измерения самого ВЦИОМ, то есть выдаёт
        сгенерированное за измеренное. В строке заголовка она не стоит ни
        пикселя высоты.
      */}
      <p className="flex items-baseline justify-between gap-2 text-xs uppercase tracking-wide text-slate">
        <span>Ценности ВЦИОМ</span>
        <span className="shrink-0 text-[10px] normal-case tracking-normal text-slate/70">
          персон аудитории · из 17
        </span>
      </p>
      <ol className="space-y-[2px]">
        {rows.map((row) => (
          <li key={row.value} className="relative h-[13px] overflow-hidden rounded-sm">
            {/*
              Дорожка и заполнение — два слоя под текстом. Ширина в процентах от
              САМОЙ ЧАСТОЙ ценности: каждая персона несёт пять, и доля от суммы
              дала бы столбики, не значащие ничего.
            */}
            <span className="absolute inset-0 bg-secondary" aria-hidden />
            <span
              className="absolute inset-y-0 left-0 bg-brand-blue/25"
              style={{ width: `${Math.round(row.share * 100)}%` }}
              aria-hidden
            />
            <span className="relative flex h-full items-center justify-between gap-2 px-1.5">
              {/*
                `truncate` с `title`: обрезанное название читается наведением, а
                перенос на вторую строку сломал бы высоту всех семнадцати строк.
              */}
              <span className="truncate text-[10px] leading-none" title={row.value}>
                {row.value}
              </span>
              <span
                className={`shrink-0 text-[10px] leading-none tabular-nums ${
                  row.count === 0 ? "text-slate" : "font-medium"
                }`}
              >
                {row.count}
              </span>
            </span>
          </li>
        ))}
      </ol>

    </div>
  );
}
