import { NextRequest, NextResponse } from "next/server";
import { loadDraft, saveDraft, type SessionUser } from "@/lib/server/mongo";
import { requireSession } from "@/lib/server/guard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ projectId: string }> },
) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { projectId } = await params;
  const user: SessionUser = {
    userId: session.user.id,
    tenantId: session.user.tenantId,
  };

  const draft = await loadDraft(user, projectId);
  return NextResponse.json({ draft });
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ projectId: string }> },
) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { projectId } = await params;
  const body = await req.json();
  const user: SessionUser = {
    userId: session.user.id,
    tenantId: session.user.tenantId,
  };

  await saveDraft(user, projectId, body);
  return NextResponse.json({ ok: true });
}