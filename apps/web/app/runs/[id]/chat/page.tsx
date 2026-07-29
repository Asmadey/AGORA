"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Send, BarChart3, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { TimecodeRef } from "@/components/agora/Primitives";
import { MOCK_PERSONAS, MOCK_STUDY } from "@/lib/mock-data";

/**
 * Чат по результатам исследования (#28).
 *
 * Два режима, потому что это два разных собеседника, а не одна фича с настройкой:
 *   «Аналитик» видит весь срез и отвечает по агрегату;
 *   «Персона» видит только свой профиль, видео и свои прежние ответы — та же
 *   структурная изоляция, что в основном пайплайне.
 *
 * Ответ без ссылки на таймкод или цитату здесь не считается ответом: интерфейс
 * показывает опору под каждой репликой, чтобы отличать факт от домысла.
 */

type Msg = {
  role: "user" | "assistant";
  text: string;
  refs?: { timecode: string; note: string }[];
  insufficient?: boolean;
};

const ANALYST_SEED: Msg[] = [
  {
    role: "user",
    text: "Почему сегмент 45+ просел по досмотру?",
  },
  {
    role: "assistant",
    text:
      "Не по оценкам, а именно по досмотру. Обе персоны сегмента 45+ поставили высокие баллы (7.5 в среднем), но прервали просмотр на сцене 34:20. Галина, 63 написала прямо: «я такое смотреть не могу, выключила и не вернулась». То есть материал им нравился до конкретного момента — это не общее отторжение, а одна точка обрыва.\n\nВажная деталь: Сергей, 49 ту же сцену оценил как оправданную сюжетом. Значит дело не в возрасте как таковом, а в границе допустимого по насилию, которая внутри сегмента различается.",
    refs: [
      { timecode: "34:20", note: "сцена насилия, точка обрыва" },
      { timecode: "18:30", note: "до этого вовлечённость высокая" },
    ],
  },
];

export default function ChatPage() {
  const [mode, setMode] = useState<"analyst" | "persona">("analyst");
  const [personaId, setPersonaId] = useState(MOCK_PERSONAS[0].id);
  const [messages, setMessages] = useState<Msg[]>(ANALYST_SEED);
  const [input, setInput] = useState("");

  const persona = MOCK_PERSONAS.find((p) => p.id === personaId)!;

  const send = () => {
    if (!input.trim()) return;
    const q = input.trim();
    setInput("");
    setMessages((m) => [
      ...m,
      { role: "user", text: q },
      {
        role: "assistant",
        text:
          mode === "analyst"
            ? "В этом исследовании такой показатель не измерялся, поэтому ответить по данным я не могу. Могу посчитать срез по имеющимся ответам персон — тогда это будет мой пересчёт, а не значение из отчёта."
            : "Не думала об этом, если честно. Я на такое внимания не обращаю.",
        insufficient: true,
      },
    ]);
  };

  return (
    <div className="mx-auto flex h-screen max-w-3xl flex-col p-8">
      <Link
        href={`/runs/${MOCK_STUDY.id}`}
        className="mb-5 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        К отчёту
      </Link>

      {/* Переключатель собеседника */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => {
            setMode("analyst");
            setMessages(ANALYST_SEED);
          }}
          className={cn(
            "inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors",
            mode === "analyst" ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50",
          )}
        >
          <BarChart3 className="h-4 w-4" />
          Аналитик
        </button>
        <button
          onClick={() => {
            setMode("persona");
            setMessages([]);
          }}
          className={cn(
            "inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors",
            mode === "persona" ? "border-foreground bg-secondary" : "border-border hover:bg-secondary/50",
          )}
        >
          <User className="h-4 w-4" />
          Спросить персону
        </button>

        {mode === "persona" && (
          <select
            value={personaId}
            onChange={(e) => {
              setPersonaId(e.target.value);
              setMessages([]);
            }}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm"
          >
            {MOCK_PERSONAS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}, {p.dna.demographics.age}
              </option>
            ))}
          </select>
        )}
      </div>

      <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
        {mode === "analyst"
          ? "Аналитик видит отчёт, ответы всех персон и разбор видео. Отвечает только по этим данным — если показателя нет, так и скажет."
          : `${persona.name} знает только свой профиль, просмотренное видео и свои прежние ответы. Она не знает, что участвует в исследовании, и не видит ответов других персон.`}
      </p>

      {/* Лента */}
      <div className="mt-6 flex-1 space-y-5 overflow-y-auto pr-2">
        {messages.length === 0 && (
          <p className="py-12 text-center text-sm text-muted-foreground">
            {mode === "persona"
              ? `Задайте вопрос — ${persona.name.split(" ")[0]} ответит как зритель после просмотра.`
              : "Спросите что-нибудь об исследовании."}
          </p>
        )}

        {messages.map((m, i) => (
          <div key={i} className={cn(m.role === "user" && "flex justify-end")}>
            <div
              className={cn(
                "max-w-[85%] rounded-lg px-4 py-3 text-sm leading-relaxed",
                m.role === "user"
                  ? "bg-secondary"
                  : "border border-border bg-[hsl(222_47%_7%)]",
              )}
            >
              {m.text.split("\n\n").map((p, j) => (
                <p key={j} className={j > 0 ? "mt-3" : ""}>
                  {p}
                </p>
              ))}

              {m.refs && m.refs.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {m.refs.map((r) => (
                    <TimecodeRef key={r.timecode} timecode={r.timecode} note={r.note} />
                  ))}
                </div>
              )}

              {m.insufficient && (
                <p className="mt-3 border-t border-border/60 pt-2 text-xs text-amber-300/70">
                  {mode === "analyst"
                    ? "Данных в исследовании нет — ответ не достроен догадкой"
                    : "Вне задокументированного профиля персоны"}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Ввод */}
      <div className="mt-5 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={
            mode === "analyst" ? "Например: какие сцены теряют внимание?" : "Ваш вопрос персоне"
          }
          className="flex-1 rounded-md border border-border bg-background px-4 py-2.5 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-muted-foreground"
        />
        <button
          onClick={send}
          className="rounded-md bg-foreground px-4 text-background transition-opacity hover:opacity-90"
          aria-label="Отправить"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Каждое сообщение — платный вызов модели и учитывается в лимите стоимости из Настроек.
      </p>
    </div>
  );
}
