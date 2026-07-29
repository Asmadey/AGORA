import { NextRequest, NextResponse } from 'next/server';
import { uploadVideoToGemini } from '@/lib/ai-server';
import fs from 'fs';
import os from 'os';
import path from 'path';

export const runtime = 'nodejs';
export const maxDuration = 60;

export async function POST(req: NextRequest) {
  let tempPath = '';
  try {
    const { url } = await req.json();
    if (!url) return NextResponse.json({ error: 'URL не указан.' }, { status: 400 });

    // Gemini cannot natively fetch YouTube; treat as a text link.
    if (url.includes('youtube.com') || url.includes('youtu.be')) {
      return NextResponse.json({ isTextLink: true, url, originalName: url });
    }

    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Не удалось скачать файл: ${resp.statusText}`);
    const mimeType = resp.headers.get('content-type') || 'video/mp4';
    const buffer = Buffer.from(await resp.arrayBuffer());
    tempPath = path.join(os.tmpdir(), `agora_url_${Date.now()}.mp4`);
    fs.writeFileSync(tempPath, buffer);

    const result = await uploadVideoToGemini(tempPath, mimeType, url.split('/').pop() || url);
    return NextResponse.json(result);
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'URL upload error' }, { status: 500 });
  } finally {
    if (tempPath && fs.existsSync(tempPath)) fs.unlinkSync(tempPath);
  }
}
