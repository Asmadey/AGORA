import { withTenant } from "@/lib/server/db";
import { requireOwner, toResponse } from "@/lib/server/guard";
import { upsertDistilledPortrait } from "@/lib/server/portraits";

/**
 * API портретов аудитории (задача #24) — авто-дистилляция из корпуса.
 *
 * POST /api/portraits/distill — запускает авто-дистилляцию, создаёт портреты
 *   в базе для каждого сегмента. Только owner.
 *
 * Дистилляция работает в двух режимах:
 * 1. Детерминированный (по умолчанию) — агрегация статистики корпуса без LLM.
 *    Гарантирует непустой, заземлённый портрет в любой среде.
 * 2. LLM — если задан OPENAI_API_KEY, вызывается модель с промптом portrait.distill.
 *
 * Запрос: { "use_llm"?: boolean, "segment"?: string }
 * Если segment не задан — дистиллируются все сегменты.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface DistillBody {
  use_llm?: boolean;
  segment?: string;
}

interface DistillResult {
  segment: string;
  name: string;
  body_md: string;
}

export async function POST(request: Request) {
  try {
    const { userId, tenantId } = await requireOwner();

    let body: DistillBody = {};
    try {
      body = (await request.json()) as DistillBody;
    } catch {
      // Empty body is OK — distill all segments with defaults
    }

    const useLlm = body.use_llm ?? false;
    const segmentFilter = body.segment;

    // Run the Python distill module via subprocess.
    // The agent-core service owns the distillation logic; the web layer
    // orchestrates and persists results.
    const { execFile } = await import("node:child_process");
    const { promisify } = await import("node:util");
    const execFileAsync = promisify(execFile);

    const repoRoot = process.env.AGORA_REPO_ROOT || process.cwd();
    const pythonScript = `${repoRoot}/services/agent-core/agent_core/portraits/distill.py`;
    const args = [pythonScript, "--json"];
    if (!useLlm) {
      args.push("--no-llm");
    }

    let results: DistillResult[] = [];
    try {
      const { stdout } = await execFileAsync("python3", args, {
        cwd: repoRoot,
        timeout: 120_000,
        maxBuffer: 10 * 1024 * 1024,
        env: { ...process.env },
      });

      // Parse JSON output — the script outputs a JSON array when --json is passed
      results = JSON.parse(stdout) as DistillResult[];
    } catch (err) {
      // Fallback: run distillation inline via a simpler approach.
      // If Python is not available, we can't distill — return error.
      const msg = err instanceof Error ? err.message : String(err);
      return Response.json(
        { error: `дистилляция не удалась: ${msg.slice(0, 200)}` },
        { status: 500 },
      );
    }

    // Filter by segment if requested
    if (segmentFilter) {
      results = results.filter((r) => r.segment === segmentFilter);
    }

    // ─── Запись: по записи на сегмент, а не по комплекту на запуск ──────────
    // Прежняя версия звала `createPortrait` и добавляла новый портрет на
    // каждый запуск. Десять запусков дали десять комплектов на одни и те же
    // сегменты, и воркеру, который ищет портрет ПО СЕГМЕНТУ, доставался тот,
    // кто раньше попался.
    //
    // Сегмент — то единственное, по чему воркер найдёт портрет при сборке
    // персоны, и запись по нему одна. Без сегмента дистилляция даёт красивый
    // текст, который никогда никем не прочитается, — такой пропускается с
    // объяснением, а не пишется молча.
    const skipped: string[] = [];
    const portraits = await withTenant(tenantId, async (client) => {
      const saved = [];
      for (const result of results) {
        if (!result.segment?.trim()) {
          skipped.push(result.name);
          continue;
        }
        saved.push(
          await upsertDistilledPortrait(
            client,
            result.name,
            result.body_md,
            result.segment,
            userId,
          ),
        );
      }
      return saved;
    });

    return Response.json({
      portraits,
      count: portraits.length,
      method: useLlm ? "llm" : "deterministic",
      skipped,
    });
  } catch (error) {
    return toResponse(error);
  }
}