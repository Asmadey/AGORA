"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Send, BarChart3, User } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  parseChatEvent,
  replyNote,
  type ChatFlags,
  type ChatMessage,
  type ChatMode,
} from "@/lib/chat";

/**
 * Лента чата по результатам исследования (#28).
 *
 * ─── Что здесь НЕ делается ────────────────────────────────────────────────
 * Не разбирается метаблок и не проверяется опора: и то и другое считает
 * воркер той же функцией, что отсеивает утверждения в отчёте. Вторая
 * реализация на TypeScript разошлась бы с первой — молча, как расходится всё,
 * что написано дважды.
 *
 * ─── Про поток ────────────────────────────────────────────────────────────
 * Ответ появляется словами. Признак опоры приходит последним событием, то есть
 * когда текст уже прочитан, — поэтому подпись «без опоры на материал»
 * появляется ПОД готовым ответом, а не вместо него. Убирать показанное нельзя:
 * исчезающий текст читается как поломка, а не как проверка.
 */

export function ChatView({
  runId,
  mode,
  personaId,
  personaName,
}: {
  runId: string;
  mode: ChatMode;
  personaId?: string;
  personaName?: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const q = new URLSearchParams({ mode, ...(personaId ? { personaId } : {}) });
    fetch(`/api/runs/${runId}/chat?${q}`)
      .then((r) => (r.ok ? r.json() : { messages: [] }))
      .then((d) => {
        if (!alive) return;
        setMessages(
          (d.messages ?? []).map((m: Record<string, unknown>) => ({
            id: String(m.id),
            role: m.role === "assistant" ? "assistant" : "user",
            content: String(m.content ?? ""),
            flags: (m.flags ?? undefined) as ChatFlags | undefined,
          })),
        );
      })
      .catch(() => alive && setMessages([]));
    return () => {
      alive = false;
    };
  }, [runId, mode, personaId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  async function send() {
    const question = draft.trim();
    if (!question || streaming) return;

    setDraft("");
    setError(null);
    setStreaming(true);
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: question };
    const replyId = `a-${Date.now()}`;
    setMessages((prev) => [...(prev ?? []), userMsg, { id: replyId, role: "assistant", content: "" }]);

    try {
      const res = await fetch(`/api/runs/${runId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, question, personaId }),
      });

      if (!res.ok || !res.body) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.error ?? `сервер ответил ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Последняя строка может быть недописанной — оставляем её в буфере.
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const event = parseChatEvent(line);
          if (!event) continue;
          if (event.kind === "error") throw new Error(event.message);
          setMessages((prev) =>
            (prev ?? []).map((m) => {
              if (m.id !== replyId) return m;
              if (event.kind === "delta") return { ...m, content: m.content + event.text };
              return { ...m, content: event.answer || m.content, flags: event.flags };
            }),
          );
        }
      }
    } catch (e) {
      setError((e as Error).message);
      // Пустая заготовка ответа убирается: пузырь без текста выглядит как
      // ответ, которого не было.
      setMessages((prev) => (prev ?? []).filter((m) => !(m.id === replyId && !m.content)));
    } finally {
      setStreaming(false);
    }
  }

  const Icon = mode === "analyst" ? BarChart3 : User;
  const who = mode === "analyst" ? "Аналитик" : personaName || "Персона";

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="min-h-[24rem] flex-1 space-y-4 overflow-y-auto rounded-lg border border-hairline bg-card p-6">
        {messages === null && (
          <p className="text-sm text-slate">Загрузка разговора…</p>
        )}

        {messages?.length === 0 && (
          <div className="flex gap-3 text-sm text-slate">
            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
            <p className="leading-relaxed">
              {mode === "analyst"
                ? "Спросите про результаты: почему просел сегмент, из чего сложился NPS, что говорили о конкретной сцене. Ответ придёт со ссылкой на таймкод или цитату."
                : `Задайте вопрос персоне. Она помнит только материал и свои прежние ответы — чужих не знает.`}
            </p>
          </div>
        )}

        {messages?.map((m) => {
          const note = m.role === "assistant" && m.flags ? replyNote(m.flags, mode) : "";
          return (
            <div key={m.id} className={cn("flex", m.role === "user" && "justify-end")}>
              <div
                className={cn(
                  "max-w-[46rem] rounded-lg px-4 py-3 text-sm leading-relaxed",
                  m.role === "user" ? "bg-secondary" : "border border-hairline",
                )}
              >
                {m.role === "assistant" && (
                  <p className="mb-1.5 text-xs font-medium text-slate">{who}</p>
                )}
                <p className="whitespace-pre-wrap">
                  {m.content}
                  {streaming && !m.content && m.role === "assistant" && (
                    <span className="text-slate">…</span>
                  )}
                </p>
                {note && (
                  <p className="mt-2 border-t border-hairline pt-2 text-xs leading-relaxed text-warning">
                    {note}
                  </p>
                )}
              </div>
            </div>
          );
        })}
        <div ref={bottom} />
      </div>

      {error && (
        <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>
      )}

      <div className="flex items-end gap-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Enter отправляет, Shift+Enter переносит строку: вопрос обычно в
            // одну строку, и тянуться к кнопке на каждом — лишнее движение.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          rows={2}
          placeholder={mode === "analyst" ? "Вопрос по результатам…" : "Вопрос персоне…"}
          className="flex-1 resize-none rounded-md border border-hairline bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-muted-foreground/60"
        />
        <button
          type="button"
          onClick={() => void send()}
          disabled={streaming || !draft.trim()}
          className="inline-flex items-center gap-2 rounded-md bg-foreground px-4 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Спросить
        </button>
      </div>

      <p className="text-xs leading-relaxed text-slate">
        Каждая реплика — платный вызов модели и считается в тот же потолок, что и прогон
        («Кап стоимости» в Настройках). Разговор сохраняется и переживает перезагрузку.
      </p>
    </div>
  );
}
