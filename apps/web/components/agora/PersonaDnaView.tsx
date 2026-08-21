import { Chip } from "@/components/agora/Primitives";
import { categoryLabel, fieldLabel, SCALE_1_5 } from "@/lib/persona-dna-labels";

/**
 * Отрисовка DNA персоны — общая для полной карточки и для попапа в отчёте.
 *
 * ─── Почему обход структурой, а не перечисление полей ──────────────────────
 * Требование cdd #6: «присутствует КАЖДОЕ непустое поле DNA — ни одно поле не
 * потеряно при рендере». Перечисленный вручную список это требование не
 * удерживает: добавили поле в canonical JSON Schema — карточка про него не
 * знает, и заметить это можно только глазами.
 *
 * Здесь обходится фактический объект DNA. Новое поле появляется на экране само;
 * словарь подписей влияет лишь на то, будет ли у него русское название или имя
 * из схемы.
 *
 * ─── Почему это отдельный компонент ────────────────────────────────────────
 * Тех же данных стало два потребителя: страница `/personas/[id]` и попап «О
 * персоне» в карточке ответа. Написанные порознь, они разошлись бы — сначала
 * подписями, потом составом полей, — и требование «ни одно поле не потеряно»
 * выполнялось бы ровно в том из них, куда посмотрели последним.
 *
 * Файл намеренно без «use client»: разметка чистая, серверных импортов нет,
 * поэтому он годится и серверному дереву страницы, и клиентскому дереву попапа.
 */

/** Шкала 1–5: число без максимума не читается. */
function Scale({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="flex gap-0.5" aria-hidden>
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className={`h-1.5 w-4 rounded-sm ${i <= value ? "bg-foreground/70" : "bg-border"}`}
          />
        ))}
      </span>
      <span className="text-xs text-slate">{value} из 5</span>
    </span>
  );
}

function renderValue(key: string, value: unknown) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-slate">—</span>;
    return (
      <span className="flex flex-wrap gap-1">
        {value.map((v, i) => (
          <Chip key={`${String(v)}-${i}`} tone="outline">
            {String(v)}
          </Chip>
        ))}
      </span>
    );
  }
  if (typeof value === "number" && SCALE_1_5.has(key)) return <Scale value={value} />;
  if (value === null || value === undefined || value === "") {
    return <span className="text-slate">—</span>;
  }
  return <span>{String(value)}</span>;
}

export function PersonaDnaView({
  dna,
  narrative,
  columns = 2,
}: {
  dna: Record<string, unknown>;
  narrative?: string | null;
  /** В попапе одна колонка: ширина диалога вдвое меньше страницы. */
  columns?: 1 | 2;
}) {
  const categories = Object.entries(dna).filter(
    ([, v]) => v !== null && typeof v === "object" && !Array.isArray(v),
  ) as [string, Record<string, unknown>][];

  return (
    <>
      {narrative && (
        <section className="mb-4 rounded-lg border border-hairline bg-card p-5">
          <h2 className="text-sm font-semibold">Описание</h2>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate">
            {narrative}
          </p>
        </section>
      )}

      <div className={`grid gap-4 ${columns === 2 ? "md:grid-cols-2" : ""}`}>
        {categories.map(([category, fields]) => (
          <section key={category} className="rounded-lg border border-hairline bg-card p-5">
            <h2 className="text-sm font-semibold">{categoryLabel(category)}</h2>
            <div className="mt-3">
              <dl className="space-y-2 text-sm">
                {Object.entries(fields).map(([key, value]) => (
                  <div key={key} className="flex flex-wrap items-baseline gap-x-2">
                    <dt className="text-slate">{fieldLabel(key)}:</dt>
                    <dd>{renderValue(key, value)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
