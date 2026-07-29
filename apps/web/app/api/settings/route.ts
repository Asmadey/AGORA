import { NextResponse } from "next/server";
import { DEFAULT_SETTINGS, parseSettings, type TenantSettings } from "@/lib/settings";

/**
 * Настройки арендатора (задача #27).
 *
 * ЭТАП 1 из 2. Контракт и валидация — настоящие; хранилище — временное.
 *
 * Значения лежат в памяти процесса, а не в Postgres, потому что таблица settings
 * scoped по tenant_id, а tenant_id берётся из сессии Auth.js — то есть до задачи #3
 * писать в базу физически некуда: не существует арендатора, от чьего имени идёт
 * запись. Класть настройки в БД без tenant_id значит завести строку, которую потом
 * придётся мигрировать вручную и которая до миграции видна всем.
 *
 * Что переживёт переезд на БД без изменений: форма запроса и ответа, валидация в
 * lib/settings.ts, поведение интерфейса. Меняются только две строки ниже —
 * чтение и запись.
 *
 * ВНИМАНИЕ: память процесса обнуляется при перезапуске сервера и не разделяется
 * между воркерами Node. Это приемлемо ровно потому, что это заглушка на один шаг.
 */

export const dynamic = "force-dynamic";

let stored: TenantSettings = { ...DEFAULT_SETTINGS };

export async function GET() {
  return NextResponse.json({
    settings: stored,
    persistence: "memory",
    note: "Постоянное хранение появится вместе с таблицей settings (задачи #2, #3).",
  });
}

export async function PUT(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "тело запроса не является корректным JSON" }, { status: 400 });
  }

  const parsed = parseSettings(body);
  if (!parsed.ok) {
    return NextResponse.json({ error: "настройки не прошли валидацию", details: parsed.errors }, { status: 400 });
  }

  stored = parsed.value;

  return NextResponse.json({ settings: stored, persistence: "memory" });
}
