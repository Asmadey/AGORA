import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { createProject, listProjects } from "@/lib/server/projects";

/**
 * Проекты — список и создание.
 *
 * GET  /api/projects — проекты арендатора вместе с их прогонами
 * POST /api/projects — создать проект
 *
 * Маршрут заведён вместе с переводом экранов проектов с localforage на базу.
 * Страницы читают проекты напрямую через `lib/server/projects`, а не через
 * этот маршрут: серверный компонент ходит в Postgres сам, лишний виток через
 * HTTP ничего не добавил бы. Маршрут нужен другому — тому, у чего страницы
 * нет: сквозной проверке и внешнему клиенту.
 *
 * Это не формальность. Пока проекты жили во вкладке, проверить их можно было
 * только глазами: у localforage нет адреса, по которому постучится тест.
 * Именно поэтому дефект прожил так долго.
 *
 * Создание доступно любому участнику команды, а не только owner: проект — это
 * имя и ничего больше, а исследование запускает `POST /api/tasks`, где права
 * и проверяются.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Длиннее не помещается ни в карточку, ни в заголовок экрана. */
const MAX_NAME = 200;

export async function GET() {
  try {
    const { tenantId } = await requireSession();
    const projects = await withTenant(tenantId, (client) => listProjects(client));
    return Response.json({ projects });
  } catch (error) {
    return toResponse(error);
  }
}

export async function POST(request: Request) {
  try {
    const { tenantId, userId } = await requireSession();

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json(
        { error: "тело запроса не является корректным JSON" },
        { status: 400 },
      );
    }

    const name = String((body as { name?: unknown })?.name ?? "").trim();
    if (!name) {
      return Response.json(
        { error: "требуется поле name (непустая строка)" },
        { status: 400 },
      );
    }
    if (name.length > MAX_NAME) {
      return Response.json(
        { error: `name длиннее ${MAX_NAME} символов` },
        { status: 400 },
      );
    }

    const project = await withTenant(tenantId, (client) =>
      createProject(client, { name, createdBy: userId }),
    );
    return Response.json({ project }, { status: 201 });
  } catch (error) {
    return toResponse(error);
  }
}
