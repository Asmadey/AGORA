import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "AGORA — синтетические фокус-группы",
  description:
    "Оценка видеоконтента на синтетической аудитории AI-персон, заземлённой на реальный корпус фокус-групп.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className="dark">
      <body
        suppressHydrationWarning
        className="min-h-screen bg-background font-sans text-foreground antialiased"
      >
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
