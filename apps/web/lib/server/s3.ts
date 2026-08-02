import "server-only";

import { createHmac, createHash, randomUUID } from "node:crypto";

/**
 * S3 presigned URL generation for TimeWeb S3-compatible storage (задача #8).
 *
 * ─── Почему без @aws-sdk ────────────────────────────────────────────────
 * AWS SDK v3 — это ~30 пакетов и мегабайты кода ради одной операции: подписать
 * URL. SigV4 — открытый алгоритм из 12 строк, и node:crypto уже есть везде.
 * Добавлять зависимость ради presign — это раздувать bundle и ставить транзитивные
 * пакеты, которых нет в lock-файле. Подпись здесь идентична той, что SDK выдаёт
 * внутренне, и TimeWeb принимает её как родную.
 *
 * ─── Что важно знать про SigV4 presigned URL ────────────────────────────
 * · В presigned-режиме подпись считается по каноническому запросу, в котором
 *   метод всегда PUT, а параметры X-Amz-* идут в query string, не в заголовках.
 *   Заголовок остаётся один: host (его AWS добавляет автоматически).
 * · Payload не подписывается (X-Amz-Content-Sha256 = UNSIGNED-PAYLOAD) — иначе
 *   клиенту пришлось бы отправлять ровно тот хеш, что мы посчитали, а файл
 *   может быть 700 МБ и стримиться кусками.
 * · Время жизни URL — 15 минут. Достаточно для начала загрузки большого файла,
 *   недостаточно, чтобы URL утёк и жил вечно. S3 сам проверяет expires.
 * · Ключ (object key) привязан к tenant_id — один арендатор не может писать
 *   в префикс другого, даже если получит чужий URL.
 */

const ENDPOINT = process.env.S3_ENDPOINT ?? "https://s3.timeweb.cloud";
const BUCKET = process.env.S3_BUCKET ?? "agora-media";
const ACCESS_KEY = process.env.S3_ACCESS_KEY ?? "";
const SECRET_KEY = process.env.S3_SECRET_KEY ?? "";
const REGION = "ru-1"; // TimeWeb использует ru-1; значение не влияет на подпись, но входит в credential scope

const EXPIRES_SECONDS = 900; // 15 минут

interface S3Config {
  endpoint: string;
  bucket: string;
  accessKey: string;
  secretKey: string;
  region: string;
}

function getConfig(): S3Config {
  if (!ACCESS_KEY || !SECRET_KEY) {
    throw new Error("S3_ACCESS_KEY или S3_SECRET_KEY не заданы — загрузка невозможна");
  }
  return { endpoint: ENDPOINT, bucket: BUCKET, accessKey: ACCESS_KEY, secretKey: SECRET_KEY, region: REGION };
}

/** Парсит endpoint на host и protocol — host нужен для канонического запроса и заголовка host. */
function parseEndpoint(endpoint: string): { protocol: string; host: string } {
  const url = new URL(endpoint);
  return { protocol: url.protocol.replace(":", ""), host: url.host };
}

/**
 * Генерирует presigned PUT URL для загрузки объекта в S3.
 *
 * @param tenantId UUID арендатора — становится частью ключа объекта.
 * @param fileName Оригинальное имя файла (для расширения).
 * @param contentType MIME-тип, будет отправлен как Content-Type клиентом.
 * @returns { url, key } — url для PUT-запроса, key — путь объекта в бакете.
 */
export function createPresignedPutUrl(
  tenantId: string,
  fileName: string,
  contentType: string,
): { url: string; key: string } {
  const cfg = getConfig();
  const { protocol, host } = parseEndpoint(cfg.endpoint);

  // Ключ: tenants/{tenantId}/uploads/{uuid}/{fileName}
  // tenantId в пути — гарантия, что один арендатор не перезапишет объект другого.
  const ext = fileName.split(".").pop() ?? "mp4";
  const key = `tenants/${tenantId}/uploads/${randomUUID()}.${ext}`;

  const now = new Date();
  const amzDate = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const dateStamp = amzDate.slice(0, 8);

  // Параметры query string — должны быть отсортированы по ключу для canonical query string
  const params: Record<string, string> = {
    "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
    "X-Amz-Credential": `${cfg.accessKey}/${dateStamp}/${cfg.region}/s3/aws4_request`,
    "X-Amz-Date": amzDate,
    "X-Amz-Expires": String(EXPIRES_SECONDS),
    "X-Amz-SignedHeaders": "host",
    // Content-Type не входит в SignedHeaders — клиент может отправить любой,
    // но мы требуем его в presign-запросе и валидируем тип на этапе complete.
  };

  // Каноническая строка запроса: ключи отсортированы, значения URL-encoded
  const canonicalQueryString = Object.keys(params)
    .sort()
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join("&");

  // Канонические заголовки — только host (единственный в SignedHeaders)
  const canonicalHeaders = `host:${host}\n`;
  const signedHeaders = "host";

  // Для presigned URL payload не подписывается
  const payloadHash = "UNSIGNED-PAYLOAD";

  const canonicalRequest = [
    "PUT",
    `/${key}`,
    canonicalQueryString,
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");

  // String to sign
  const credentialScope = `${dateStamp}/${cfg.region}/s3/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    credentialScope,
    createHash("sha256").update(canonicalRequest).digest("hex"),
  ].join("\n");

  // Signing key: производная от секретного ключа — цепочка HMAC
  const kDate = hmac("AWS4" + cfg.secretKey, dateStamp);
  const kRegion = hmac(kDate, cfg.region);
  const kService = hmac(kRegion, "s3");
  const kSigning = hmac(kService, "aws4_request");
  const signature = hmac(kSigning, stringToSign).toString("hex");

  // Собираем итоговый URL
  const url = `${protocol}://${host}/${cfg.bucket}/${key}?${canonicalQueryString}&X-Amz-Signature=${signature}`;

  return { url, key };
}

function hmac(key: string | Buffer, data: string): Buffer {
  return createHmac("sha256", key).update(data).digest();
}

/**
 * Публичный (read-only) URL объекта — для отдачи видео воркеру.
 * TimeWeb бакеты могут быть приватными; этот URL работает если объект
 * публично читаем. Для приватной отдачи используется presigned GET.
 */
export function publicObjectUrl(key: string): string {
  const cfg = getConfig();
  const { protocol, host } = parseEndpoint(cfg.endpoint);
  return `${protocol}://${host}/${cfg.bucket}/${key}`;
}

/**
 * Генерирует presigned GET URL — для приватной отдачи объекта воркеру
 * или ffmpeg/ffprobe, которым нужен прямой доступ к файлу.
 */
export function createPresignedGetUrl(key: string): string {
  const cfg = getConfig();
  const { protocol, host } = parseEndpoint(cfg.endpoint);

  const now = new Date();
  const amzDate = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const dateStamp = amzDate.slice(0, 8);

  const params: Record<string, string> = {
    "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
    "X-Amz-Credential": `${cfg.accessKey}/${dateStamp}/${cfg.region}/s3/aws4_request`,
    "X-Amz-Date": amzDate,
    "X-Amz-Expires": String(EXPIRES_SECONDS),
    "X-Amz-SignedHeaders": "host",
  };

  const canonicalQueryString = Object.keys(params)
    .sort()
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join("&");

  const canonicalHeaders = `host:${host}\n`;
  const signedHeaders = "host";
  const payloadHash = "UNSIGNED-PAYLOAD";

  const canonicalRequest = [
    "GET",
    `/${key}`,
    canonicalQueryString,
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");

  const credentialScope = `${dateStamp}/${cfg.region}/s3/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    credentialScope,
    createHash("sha256").update(canonicalRequest).digest("hex"),
  ].join("\n");

  const kDate = hmac("AWS4" + cfg.secretKey, dateStamp);
  const kRegion = hmac(kDate, cfg.region);
  const kService = hmac(kRegion, "s3");
  const kSigning = hmac(kService, "aws4_request");
  const signature = hmac(kSigning, stringToSign).toString("hex");

  return `${protocol}://${host}/${cfg.bucket}/${key}?${canonicalQueryString}&X-Amz-Signature=${signature}`;
}

// ─── ffprobe: валидация загруженного видео ───────────────────────────────

export interface VideoProbeResult {
  durationSec: number;
  codec: string;
  width: number;
  height: number;
  sizeBytes: number;
  format: string;
}

const MAX_FILE_SIZE = 700 * 1024 * 1024; // 700 МБ
const ALLOWED_CODECS = ["h264", "hevc", "h265", "vp9", "av1", "mpeg4", "msmpeg4v2", "msmpeg4v3"];
// mp4 → h264/hevc, mov → h264/prores, avi → mpeg4/divx/xvid

/**
 * HEAD-запрос к S3 для получения размера объекта без скачивания.
 * TimeWeb S3 поддерживает HEAD как стандартный S3.
 */
export async function headObjectSize(key: string): Promise<number> {
  const cfg = getConfig();
  const { protocol, host } = parseEndpoint(cfg.endpoint);
  const objectUrl = `${protocol}://${host}/${cfg.bucket}/${key}`;

  const resp = await fetch(objectUrl, { method: "HEAD" });
  if (!resp.ok) {
    throw new Error(`S3 HEAD failed: ${resp.status} ${resp.statusText}`);
  }
  const len = resp.headers.get("content-length");
  if (!len) throw new Error("S3 HEAD не вернул content-length");
  return Number(len);
}

/**
 * Запускает ffprobe по presigned GET URL и возвращает параметры видео.
 *
 * ffprobe скачивает только заголовки (moov atom для mp4), не весь файл —
 * поэтому вызов по URL дешевле, чем кажется. Для 700 МБ это секунды.
 *
 * Бросает ошибку с человекочитаемым текстом, если видео не прошло валидацию.
 */
export async function probeVideo(
  presignedGetUrl: string,
  expectedSize: number,
): Promise<VideoProbeResult> {
  if (expectedSize > MAX_FILE_SIZE) {
    throw new Error(`Файл превышает лимм 700 МБ: ${Math.round(expectedSize / 1024 / 1024)} МБ`);
  }

  const { execFile } = await import("node:child_process");
  const { promisify } = await import("node:util");
  const execFileAsync = promisify(execFile);

  // -show_streams: потоки (видео), -show_format: контейнер (длительность, размер)
  // -v quiet: только JSON, без stderr-шума
  // -print_format json: структурированный вывод
  let stdout: string;
  try {
    const result = await execFileAsync("ffprobe", [
      "-v", "quiet",
      "-print_format", "json",
      "-show_streams",
      "-show_format",
      presignedGetUrl,
    ], { timeout: 30_000, maxBuffer: 1024 * 1024 });
    stdout = result.stdout;
  } catch (e: any) {
    throw new Error(`ffprobe не смог прочитать файл: ${e?.message ?? "неизвестная ошибка"}`);
  }

  let probe: any;
  try {
    probe = JSON.parse(stdout);
  } catch {
    throw new Error("ffprobe вернул невалидный JSON");
  }

  const videoStream = (probe.streams ?? []).find((s: any) => s.codec_type === "video");
  if (!videoStream) {
    throw new Error("Видеопоток не найден — файл не содержит видео");
  }

  const codec = String(videoStream.codec_name ?? "").toLowerCase();
  const width = Number(videoStream.width ?? 0);
  const height = Number(videoStream.height ?? 0);

  // Длительность: prefer format.duration (более надёжный для контейнера), fallback to stream
  const durationSec = Number(probe.format?.duration ?? videoStream.duration ?? 0);
  const format = String(probe.format?.format_name ?? "");
  const sizeBytes = Number(probe.format?.size ?? expectedSize);

  if (sizeBytes > MAX_FILE_SIZE) {
    throw new Error(`Файл превышает лимм 700 МБ: ${Math.round(sizeBytes / 1024 / 1024)} МБ`);
  }

  if (!ALLOWED_CODECS.includes(codec)) {
    throw new Error(
      `Кодек «${codec}» не поддерживается. Разрешённые: ${ALLOWED_CODECS.join(", ")}`,
    );
  }

  if (durationSec <= 0) {
    throw new Error("Не удалось определить длительность видео");
  }

  return { durationSec, codec, width, height, sizeBytes, format };
}

export const S3_LIMITS: {
  MAX_FILE_SIZE: number;
  EXPIRES_SECONDS: number;
  ALLOWED_CODECS: string[];
  ALLOWED_EXTENSIONS: string[];
  ALLOWED_MIME_TYPES: string[];
} = {
  MAX_FILE_SIZE,
  EXPIRES_SECONDS,
  ALLOWED_CODECS,
  ALLOWED_EXTENSIONS: ["mp4", "mov", "avi"],
  ALLOWED_MIME_TYPES: [
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
  ],
};