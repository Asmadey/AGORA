import { NextResponse } from 'next/server';
import { fetchNewsContext } from '@/lib/ai-server';

export const runtime = 'nodejs';

export async function POST() {
  try {
    const context = await fetchNewsContext();
    return NextResponse.json({ context });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'error' }, { status: 500 });
  }
}
