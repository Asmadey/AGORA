"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Trash2, UserPlus } from "lucide-react";

import type { TeamMember } from "@/lib/server/users";

/**
 * Список участников и форма заведения (этап Ж).
 *
 * ─── Про пароль ────────────────────────────────────────────────────────────
 * Пароль вводит владелец здесь и уходит прямо в хеш на сервере. Продукт его не
 * показывает, не генерирует и не пересылает: §6-бис CLAUDE.md — всё, что
 * побывало в переписке, считается скомпрометированным и требует перевыпуска, а
 * пересылать пароль безопасно продукт не умеет.
 *
 * Отсюда и формулировка подсказки: передать пароль человеку — задача владельца,
 * и делать это надо не текстом.
 */

export function UsersManager({
  members,
  isOwner,
}: {
  members: TeamMember[];
  isOwner: boolean;
}) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"owner" | "member">("member");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const add = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name: name || null, password, role }),
      });
      const payload = (await res.json().catch(() => ({}))) as {
        error?: string;
        created?: boolean;
      };
      if (!res.ok) {
        setError(payload.error ?? `не удалось завести пользователя (${res.status})`);
        return;
      }
      // Существующий пользователь получает членство, но НЕ новый пароль — иначе
      // добавление в команду стало бы способом отобрать чужой доступ. Владельцу
      // надо это сказать: иначе он решит, что задал пароль, и продиктует его.
      setNotice(
        payload.created
          ? "Пользователь заведён"
          : "Такой пользователь уже был — он добавлен в команду со своим прежним паролем",
      );
      setEmail("");
      setName("");
      setPassword("");
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (member: TeamMember) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`/api/users/${member.userId}`, { method: "DELETE" });
      if (!res.ok) {
        const payload = (await res.json().catch(() => ({}))) as { error?: string };
        setError(payload.error ?? `удаление не удалось (${res.status})`);
        return;
      }
      router.refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-6">
      {error && (
        <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>
      )}
      {notice && (
        <p className="rounded-md bg-secondary px-3 py-2 text-sm text-slate">{notice}</p>
      )}

      <div className="overflow-hidden rounded-lg border border-hairline">
        <table className="w-full text-sm">
          <thead className="border-b border-hairline bg-secondary text-left text-xs text-slate">
            <tr>
              <th className="px-4 py-2">Почта</th>
              <th className="px-4 py-2">Имя</th>
              <th className="px-4 py-2">Роль</th>
              {isOwner && <th className="px-4 py-2" />}
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.userId} className="border-b border-hairline-soft last:border-0">
                <td className="px-4 py-2">{m.email}</td>
                <td className="px-4 py-2">{m.name ?? "—"}</td>
                <td className="px-4 py-2">{m.role === "owner" ? "Владелец" : "Участник"}</td>
                {isOwner && (
                  <td className="px-4 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => void remove(m)}
                      disabled={busy}
                      aria-label={`Удалить ${m.email}`}
                      className="text-stone transition-colors hover:text-danger disabled:opacity-40"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {isOwner && (
        <div className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Добавить пользователя</h2>
          <p className="mt-0.5 text-xs text-slate">
            Пароль уходит прямо в хеш и нигде не показывается. Передайте его
            человеку не текстом — переписка считается скомпрометированной
          </p>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs text-slate">Почта</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="off"
                className="mt-1 w-full rounded-md border border-hairline bg-background px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate">Имя (необязательно)</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded-md border border-hairline bg-background px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate">Пароль — не короче 8 символов</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                className="mt-1 w-full rounded-md border border-hairline bg-background px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate">Роль</span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as "owner" | "member")}
                className="mt-1 w-full rounded-md border border-hairline bg-background px-3 py-2 text-sm"
              >
                <option value="member">Участник</option>
                <option value="owner">Владелец</option>
              </select>
            </label>
          </div>

          <button
            type="button"
            onClick={() => void add()}
            disabled={busy || !email.includes("@") || password.length < 8}
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-foreground px-4 py-2 text-sm text-background disabled:opacity-40"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
            Добавить
          </button>
        </div>
      )}
    </div>
  );
}
