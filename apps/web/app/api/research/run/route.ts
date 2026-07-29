import { NextRequest, NextResponse } from 'next/server';
import { runResearchWithVideo } from '@/lib/ai-server';

export const runtime = 'nodejs';
export const maxDuration = 300;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const report = await runResearchWithVideo({
      projectName: body.projectName,
      agents: body.agents || body.audience || [],
      survey: body.survey,
      contentDescription: body.contentDescription,
      videoUri: body.videoUri,
      videoMimeType: body.videoMimeType,
      videoUrl: body.videoUrl,
    });
    return NextResponse.json({ report });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'Research error' }, { status: 500 });
  }
}
