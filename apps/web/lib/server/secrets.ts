import "server-only";

import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

/**
 * Шифрование секретов арендатора: ключ провайдера, задаваемый из интерфейса.
 *
 * ─── Формат ────────────────────────────────────────────────────────────────
 * AES-256-GCM. На выходе один буфер: `nonce(12) || tag(16) || ciphertext`.
 * Формат обязан совпадать с `agent_core/secrets.py` — воркер расшифровывает те
 * же байты. Разойдясь, стороны дадут ошибку расшифровки посреди прогона, уже
 * после оплаченных ffmpeg и транскрипции.
 *
 * ─── Ключ шифрования ───────────────────────────────────────────────────────
 * `SETTINGS_SECRET` из окружения обоих сервисов, свёрнутый SHA-256 до 32 байт.
 * Свёртка, а не требование ровно 32 байт: иначе оператор обязан уметь
 * сгенерировать ключ нужной длины, а на практике вписывает парольную фразу — и
 * получает отказ там, где нужен работающий продукт.
 *
 * В базу ключ шифрования не попадает никогда: замок и ключ в одном ящике — это
 * не шифрование, а его имитация.
 *
 * ─── Нативные модули ───────────────────────────────────────────────────────
 * `node:crypto` — часть рантайма, не npm-пакет. §6 CLAUDE.md запрещает нативные
 * npm-модули в apps/web, и это ограничение здесь соблюдено.
 */

const NONCE_BYTES = 12;
const TAG_BYTES = 16;

export class SecretsUnavailable extends Error {
  constructor() {
    super(
      "SETTINGS_SECRET не задан в окружении: ключ провайдера негде зашифровать. " +
        "Задайте переменную для web и worker одинаковой — иначе воркер не сможет " +
        "расшифровать то, что сохранил интерфейс",
    );
  }
}

export function secretsAvailable(): boolean {
  return Boolean(process.env.SETTINGS_SECRET);
}

function encryptionKey(): Buffer {
  const secret = process.env.SETTINGS_SECRET;
  if (!secret) throw new SecretsUnavailable();
  return createHash("sha256").update(secret, "utf8").digest();
}

export function encryptSecret(plain: string): Buffer {
  const nonce = randomBytes(NONCE_BYTES);
  const cipher = createCipheriv("aes-256-gcm", encryptionKey(), nonce);
  const body = Buffer.concat([cipher.update(plain, "utf8"), cipher.final()]);
  return Buffer.concat([nonce, cipher.getAuthTag(), body]);
}

export function decryptSecret(blob: Buffer): string {
  const nonce = blob.subarray(0, NONCE_BYTES);
  const tag = blob.subarray(NONCE_BYTES, NONCE_BYTES + TAG_BYTES);
  const body = blob.subarray(NONCE_BYTES + TAG_BYTES);
  const decipher = createDecipheriv("aes-256-gcm", encryptionKey(), nonce);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(body), decipher.final()]).toString("utf8");
}

/**
 * Маска для показа в интерфейсе: `sk-1a…9f`.
 *
 * Короткие значения не показываются вовсе, а не обрезаются: у восьмисимвольного
 * ключа четыре первых и четыре последних знака — это весь ключ.
 */
export function maskSecret(plain: string): string {
  if (!plain) return "не задан";
  if (plain.length <= 12) return "задан";
  return `${plain.slice(0, 5)}…${plain.slice(-4)}`;
}
