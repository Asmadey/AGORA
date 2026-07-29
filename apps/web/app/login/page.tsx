"use client";

import { Suspense, useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Loader2 } from "lucide-react";

/**
 * Вход (задача #3).
 *
 * Сообщение об ошибке намеренно одно на все случаи отказа. Разделение на
 * «пользователь не найден» и «неверный пароль» удобно ровно один раз — когда
 * ошибся владелец учётной записи, — и полезно постоянно тому, кто подбирает
 * адреса: ответ сервера подтверждает, что такой человек в системе есть.
 */
function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const callbackUrl = params.get("callbackUrl") ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);

    // redirect: false — иначе Auth.js уведёт на свою страницу ошибки, и форма
    // потеряет уже введённые данные вместе с объяснением, что произошло.
    const result = await signIn("credentials", { email, password, redirect: false });

    if (result?.error) {
      setError("Неверная почта или пароль");
      setPending(false);
      return;
    }

    router.push(callbackUrl);
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-sm space-y-5">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">AGORA</h1>
        <p className="text-sm text-muted-foreground">Вход в рабочее пространство команды</p>
      </div>

      <div className="space-y-2">
        <label htmlFor="email" className="text-sm font-medium">
          Почта
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="password" className="text-sm font-medium">
          Пароль
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={pending}
        className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-primary text-sm font-medium text-primary-foreground disabled:opacity-60"
      >
        {pending && <Loader2 className="h-4 w-4 animate-spin" />}
        Войти
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Suspense fallback={<Loader2 className="h-5 w-5 animate-spin" />}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
