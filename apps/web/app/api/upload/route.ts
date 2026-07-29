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
    const form = await req.formData();
    const file = form.get('video');
    if (!file || typeof file === 'string') {
      return NextResponse.json({ error: 'Файл не был загружен.' }, { status: 400 });
    }
    const blob = file as File;
    const bytes = Buffer.from(await blob.arrayBuffer());
    tempPath = path.join(os.tmpdir(), `agora_${Date.now()}_${blob.name || 'video'}`);
    fs.writeFileSync(tempPath, bytes);

    const result = await uploadVideoToGemini(
      tempPath,
      blob.type || 'video/mp4',
      blob.name || 'video'
    );
    return NextResponse.json(result);
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'Upload error' }, { status: 500 });
  } finally {
    if (tempPath && fs.existsSync(tempPath)) fs.unlinkSync(tempPath);
  }
}
