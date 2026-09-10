import { withTenant } from "@/lib/server/db";
import { buildSettingsSnapshot } from "@/lib/server/tasks";
import { requireSession, toResponse } from "@/lib/server/guard";
import { chatBudget, type ChatMode } from "@/lib/chat";

/**
 * Чат по результатам исследования (#28).
 *
 * ─── Что делает веб, а что служба агента ──────────────────────────────────
 * Веб отвечает за ДОСТУП и за ПАМЯТЬ: сессия, принадлежность прогона
 * арендатору, треды и сообщения в Postgres под RLS, потолок вызовов.
 *
 * Агент отвечает за МОДЕЛЬ: срез данных, промпты, вызов, разбор метаблока,
 * проверку опоры. Он живёт в образе воркера, потому что в образе веба нет
 * `openai`, а вторая реализация разбора промптов и `has_support` на TypeScript
 * разошлась бы с первой — этот класс дефекта в проекте повторялся трижды.
 *
 * Служба не опубликована наружу: ни портов, ни маршрута в nginx. Единственный,
 * кто её зовёт, — этот файл, и зовёт уже после проверки сессии.
 *
 * ─── Почему поток проксируется, а не пересобирается ───────────────────────
 * Ответ идёт словами (решение владельца). Веб отдаёт куски как есть и лишь в
 * конце дописывает сообщение в базу: разбирать поток дважды — на сервере и в
 * браузере — значит завести два разбора одного формата.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Адрес службы агента во внутренней сети compose. */
const AGENT_URL = process.env.AGENT_API_URL || "http://agent-api:8001";

/** Сколько последних сообщений уезжает в контекст. */
const HISTORY_LIMIT = 20;

interface Body {
  mode?: unknown;
  question?: unknown;
  personaId?: unknown;
  threadId?: unknown;
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: runId } = await params;
    const { tenantId, userId } = await requireSession();
    const body = (await request.json()) as Body;

    const mode: ChatMode = body.mode === "persona" ? "persona" : "analyst";
    const question = typeof body.question === "string" ? body.question.trim() : "";
    if (!question) {
      return Response.json({ error: "вопрос пуст" }, { status: 400 });
    }
    if (mode === "persona" && typeof body.personaId !== "string") {
      return Response.json(
        { error: "в режиме допроса персоны нужен personaId" },
        { status: 400 },
      );
    }

    const prepared = await withTenant(tenantId, async (client) => {
      // Прогон читается под арендатором: чужой сюда не попадёт, и «нет такого»
      // неотличимо от «чужой» — так и должно быть.
      const { rows: taskRows } = await client.query<{
        status: string;
        settings_snapshot: Record<string, unknown> | null;
        prompts_snapshot: Record<string, unknown> | null;
      }>(
        "SELECT status, settings_snapshot, prompts_snapshot FROM tasks WHERE id = $1::uuid",
        [runId],
      );
      const task = taskRows[0];
      if (!task) return { error: "прогон не найден", status: 404 } as const;
      if (task.status !== "REPORT_READY") {
        // Чат живёт поверх ЗАВЕРШЁННОГО прогона: спрашивать про отчёт, которого
        // ещё нет, значит получать ответ по пустому срезу.
        return {
          error: "исследование ещё не завершено — обсуждать пока нечего",
          status: 409,
        } as const;
      }

      // Тред: один на режим и персону. Переоткрытая вкладка продолжает
      // разговор, а не начинает новый, — иначе история теряется молча.
      const { rows: threadRows } = await client.query<{ id: string }>(
        `INSERT INTO chat_threads (tenant_id, task_id, mode, persona_id, created_by)
         VALUES ($1, $2::uuid, $3, $4::uuid, $5::uuid)
         ON CONFLICT DO NOTHING
         RETURNING id`,
        [tenantId, runId, mode, mode === "persona" ? body.personaId : null, userId],
      );
      let threadId = threadRows[0]?.id ?? null;
      if (!threadId) {
        const { rows } = await client.query<{ id: string }>(
          `SELECT id FROM chat_threads
            WHERE task_id = $1::uuid AND mode = $2
              AND persona_id IS NOT DISTINCT FROM $3::uuid
            ORDER BY created_at LIMIT 1`,
          [runId, mode, mode === "persona" ? body.personaId : null],
        );
        threadId = rows[0]?.id ?? null;
      }
      if (!threadId) return { error: "не удалось открыть тред", status: 500 } as const;

      const { rows: history } = await client.query<{ role: string; content: string }>(
        `SELECT role, content FROM chat_messages
          WHERE thread_id = $1::uuid ORDER BY created_at DESC LIMIT $2`,
        [threadId, HISTORY_LIMIT],
      );

      // Реплики считаются по ВСЕМУ прогону, а не по треду: кап общий с
      // прогоном, и обойти его, открыв второй тред, было бы странно.
      const { rows: usedRows } = await client.query<{ n: string }>(
        `SELECT count(*) AS n FROM chat_messages m
           JOIN chat_threads t ON t.id = m.thread_id
          WHERE t.task_id = $1::uuid AND m.role = 'assistant'`,
        [runId],
      );

      await client.query(
        "INSERT INTO chat_messages (tenant_id, thread_id, role, content) VALUES ($1, $2::uuid, 'user', $3)",
        [tenantId, threadId, question],
      );

      // Прогоны, поставленные до появления снимка настроек, его не имеют.
      // Для них читаются текущие настройки — это запасной путь, а не норма:
      // снимок главнее, потому что описывает условия ТОГО прогона.
      const settingsSnapshot =
        task.settings_snapshot && Object.keys(task.settings_snapshot).length > 0
          ? task.settings_snapshot
          : await buildSettingsSnapshot(client);

      return {
        threadId,
        used: Number(usedRows[0]?.n ?? 0),
        history: history.reverse(),
        promptsSnapshot: task.prompts_snapshot ?? {},
        settingsSnapshot,
      } as const;
    });

    if ("error" in prepared) {
      return Response.json({ error: prepared.error }, { status: prepared.status });
    }

    // Потолок берётся из снимка прогона, а не из настроек на сейчас: правка
    // настроек не должна менять условия разговора, начатого вчера. Настройки
    // читаются только как запасной путь для прогонов без снимка.
    const snapshot = prepared.settingsSnapshot as { costCap?: unknown; costCapValue?: unknown };
    const budget = chatBudget(
      {
        costCap: snapshot.costCap === "hard" ? "hard" : "auto",
        costCapValue: Number(snapshot.costCapValue),
      },
      prepared.used,
    );
    if (!budget.allowed) {
      return Response.json({ error: budget.reason }, { status: 429 });
    }

    const upstream = await fetch(`${AGENT_URL}/api/chat/reply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenant_id: tenantId,
        task_id: runId,
        mode,
        question,
        persona_id: mode === "persona" ? body.personaId : null,
        history: prepared.history,
        prompts_snapshot: prepared.promptsSnapshot,
      }),
    });

    if (!upstream.ok || !upstream.body) {
      const detail = await upstream.text().catch(() => "");
      return Response.json(
        {
          error:
            `служба чата ответила ${upstream.status}. ` +
            (detail.slice(0, 200) || "Проверьте, поднят ли контейнер agent-api."),
        },
        { status: 502 },
      );
    }

    // Поток отдаётся как есть, а собранный ответ дописывается в базу в конце.
    // Разбор идёт здесь один раз: в браузере он нужен только для отрисовки.
    const stream = new ReadableStream({
      async start(controller) {
        const reader = upstream.body!.getReader();
        const decoder = new TextDecoder();
        let tail = "";
        let finalAnswer = "";
        let finalFlags: Record<string, unknown> = {};

        try {
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            controller.enqueue(new TextEncoder().encode(text));

            tail += text;
            for (const line of tail.split("\n")) {
              if (!line.startsWith("data:")) continue;
              try {
                const payload = JSON.parse(line.slice(5).trim()) as Record<string, unknown>;
                if (payload.done && typeof payload.done === "object") {
                  const d = payload.done as Record<string, unknown>;
                  finalAnswer = typeof d.answer === "string" ? d.answer : "";
                  finalFlags = d;
                }
              } catch {
                // Незакрытая строка догрузится следующим куском.
              }
            }
            tail = tail.slice(Math.max(0, tail.lastIndexOf("\n")));
          }
        } finally {
          controller.close();
          if (finalAnswer) {
            // Ответ сохраняется даже если вкладку закрыли: разговор обязан
            // восстанавливаться, а не пропадать вместе с окном.
            await withTenant(tenantId, (client) =>
              client.query(
                `INSERT INTO chat_messages (tenant_id, thread_id, role, content, citations, flags)
                 VALUES ($1, $2::uuid, 'assistant', $3, $4::jsonb, $5::jsonb)`,
                [
                  tenantId,
                  prepared.threadId,
                  finalAnswer,
                  JSON.stringify(finalFlags.citations ?? []),
                  JSON.stringify(finalFlags),
                ],
              ),
            ).catch(() => undefined);
          }
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    return toResponse(error);
  }
}

/** История разговора — чтобы вкладка, открытая заново, показала прежние реплики. */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: runId } = await params;
    const { tenantId } = await requireSession();
    const url = new URL(request.url);
    const mode = url.searchParams.get("mode") === "persona" ? "persona" : "analyst";
    const personaId = url.searchParams.get("personaId");

    const messages = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<{
        id: string;
        role: string;
        content: string;
        flags: Record<string, unknown> | null;
      }>(
        `SELECT m.id, m.role, m.content, m.flags
           FROM chat_messages m
           JOIN chat_threads t ON t.id = m.thread_id
          WHERE t.task_id = $1::uuid AND t.mode = $2
            AND t.persona_id IS NOT DISTINCT FROM $3::uuid
          ORDER BY m.created_at`,
        [runId, mode, personaId],
      );
      return rows;
    });

    return Response.json({ messages });
  } catch (error) {
    return toResponse(error);
  }
}
