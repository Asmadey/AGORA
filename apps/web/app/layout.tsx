import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { Providers } from "@/components/Providers";
import { NO_FLASH_SCRIPT } from "@/lib/theme";
import { auth } from "@/lib/server/auth";

export const metadata: Metadata = {
  title: "AGORA — синтетические фокус-группы",
  description:
    "Оценка видеоконтента на синтетической аудитории AI-персон, заземлённой на реальный корпус фокус-групп.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Сессия снимается ЗДЕСЬ, а не в браузере: без начального значения
  // `useSession()` на серверной отрисовке отвечает «загружается», `AppShell`
  // прячет за этим всё меню, и в отправленном HTML левой колонки нет. Тогда
  // содержимое появляется раньше каркаса — порядок, обратный нужному.
  //
  // Цена — проверка подписи куки, без обращения к базе: Credentials-провайдер
  // работает только со стратегией JWT.
  const session = await auth();

  return (
    // Класса темы здесь нет намеренно. Раньше стояло className="dark" — тема
    // была прибита к разметке, и переключать было нечего. Теперь класс ставит
    // скрипт ниже, до первой отрисовки, по сохранённому выбору или по системе.
    <html lang="ru" suppressHydrationWarning>
      <head>
        {/* До загрузки любого бандла: иначе выбравший тёмную тему увидит
            однокадровую вспышку светлой, а однокадровая вспышка читается как
            дефект рендера, а не как задержка. */}
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_SCRIPT }} />
      </head>
      <body
        suppressHydrationWarning
        className="min-h-screen bg-background font-sans text-foreground antialiased"
      >
        <Providers session={session}>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
