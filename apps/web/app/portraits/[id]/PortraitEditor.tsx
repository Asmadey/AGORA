"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { ErrorState } from "@/components/agora/States";

/**
 * Правка портрета аудитории.
 *
 * ─── Почему сырой markdown, а не форма по секциям ──────────────────────────
 * Портрет — это текст с фиксированными секциями, но состав секций задаёт
 * промпт дистилляции, а не интерфейс. Форма по секциям пришлось бы менять
 * каждый раз вслед за промптом, и расхождение между ними было бы невидимым:
 * поле, которого нет в форме, просто исчезло бы из портрета при первом
 * сохранении.
 *
 * ─── Каждое сохранение — новая версия ──────────────────────────────────────
 * `PUT` пишет строку в `audience_portrait_versions`, поэтому откатиться можно
 * всегда. Это важнее удобства: портрет управляет генерацией всех последующих
 * персон, и неудачная правка меняет состав аудитории в прогонах, которые
 * запустят после неё.
 */
export function PortraitEditor({
  portraitId,
  initialName,
  initialBody,
}: {
  portraitId: string;
  initialName: string;
  initialBody: string;
}) {
  const router = useRouter();
  const [name, setName] = useState(initialName);
  const [body, setBody] = useState(initialBody);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty = name !== initialName || body !== initialBody;

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await fetch(`/api/portraits/${portraitId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), bodyMd: body }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        // 403 здесь — не поломка: правка портрета доступна только владельцу
        // команды. Общее «не удалось сохранить» отправило бы искать дефект.
        setError(
          res.status === 403
            ? "Портреты правит только владелец команды. Ваша роль — участник."
            : (payload.error ?? `сервер ответил ${res.status}`),
        );
        return;
      }
      setSaved(true);
      router.refresh();
    } catch (e) {
      setError(`запрос не дошёл: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label htmlFor="portrait-name" className="block text-sm font-medium">
          Название
        </label>
        <input
          id="portrait-name"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setSaved(false);
          }}
          maxLength={200}
          className="w-full max-w-xl rounded-md border border-input bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-ring"
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="portrait-body" className="block text-sm font-medium">
          Текст портрета
        </label>
        <textarea
          id="portrait-body"
          value={body}
          onChange={(e) => {
            setBody(e.target.value);
            setSaved(false);
          }}
          spellCheck={false}
          rows={26}
          className="w-full resize-y rounded-lg border border-input bg-background p-4 font-mono text-[13px] leading-relaxed outline-none transition-colors focus:border-ring"
        />
        <p className="text-xs text-slate">
          Доли в соцдем-профиле — часть контракта с данными, а не подпись: по ним
          калибруются персоны. Округление в тексте станет смещением в выборке.
        </p>
      </div>

      {error && <ErrorState title="Портрет не сохранён" reason={error} />}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving || !dirty || !name.trim()}
          className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-ink/90 disabled:opacity-40"
        >
          {saving ? (
            <span className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Сохранение…
            </span>
          ) : (
            "Сохранить новую версию"
          )}
        </button>
        {saved && <span className="text-sm text-success">Сохранено</span>}
        {dirty && !saved && <span className="text-sm text-slate">Есть несохранённые правки</span>}
      </div>
    </div>
  );
}
