/**
 * Загрузка ролика в S3 с настоящим прогрессом.
 *
 * ─── Почему XMLHttpRequest, а не fetch ─────────────────────────────────────
 * `fetch` не сообщает прогресса отправки в принципе: у него нет события на
 * выгруженные байты, и `ReadableStream` в теле запроса поддерживается не
 * везде. Единственный способ узнать, сколько ушло, — `xhr.upload.onprogress`.
 *
 * Это не вкус. Ролик весит до 700 МБ, заливка идёт минуты, и всё это время
 * пользователь видел неопределённый спиннер и слово «Загружается…». Отличить
 * идущую заливку от повисшей было нечем, а на четвёртом шаге визарда
 * появлялось «не приложен материал» — верное по сути и необъяснимое на вид.
 *
 * ─── Три фазы, а не две ────────────────────────────────────────────────────
 * После последнего отправленного байта работа не закончена: `complete` гоняет
 * ffprobe по контейнеру, кодекам и длительности, и файл может быть отвергнут.
 * Поэтому между «uploading» и «done» есть «checking»: написать «готово» раньше
 * ответа значит пообещать принятый материал, который может не приняться, —
 * и тогда «100%» сменится ошибкой на ровном месте.
 */

export type UploadPhase = "idle" | "presigning" | "uploading" | "checking" | "done" | "failed";

export interface UploadState {
  phase: UploadPhase;
  /** Отправлено байт. */
  sent: number;
  /** Всего байт. Ноль — размер неизвестен. */
  total: number;
  error?: string;
}

/** Человеческий размер. Двоичные килобайты — файловые менеджеры считают так же. */
function bytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value < 1024) return `${value} Б`;
  const units = ["КБ", "МБ", "ГБ"];
  let v = value / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u += 1;
  }
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[u]}`;
}

/**
 * Процент отправленного или `null`, если размер неизвестен.
 *
 * `null`, а не ноль: ноль означал бы «ничего не отправлено», то есть неправду
 * про идущую заливку. Полоса в таком случае обязана быть неопределённой.
 *
 * Округление вниз намеренно: `Math.round` показал бы 100% на 999 999 байтах из
 * миллиона, то есть до того, как последний байт ушёл.
 */
export function uploadPercent(state: UploadState): number | null {
  if (state.total <= 0) return null;
  if (state.phase === "checking" || state.phase === "done") return 100;
  return Math.min(99, Math.floor((state.sent / state.total) * 100));
}

/** Подпись под полосой. Пустая строка — показывать нечего. */
export function uploadProgressLabel(state: UploadState): string {
  if (state.phase === "failed") return state.error ?? "загрузка не удалась";
  if (state.phase === "idle") return "";
  if (state.phase === "presigning") return "Готовим загрузку…";
  // Именно «проверяем», а не «готово»: ffprobe ещё может отвергнуть файл.
  if (state.phase === "checking") return "Проверяем файл…";
  if (state.phase === "done") return "Материал принят";

  const pct = uploadPercent(state);
  const volume = state.total > 0 ? ` · ${bytes(state.sent)} из ${bytes(state.total)}` : "";
  return pct === null ? `Загрузка${volume}` : `Загрузка: ${pct}%${volume}`;
}

/**
 * Отправляет тело в S3 по подписанной ссылке, сообщая прогресс.
 *
 * Промис отклоняется с внятной причиной: сетевой обрыв и отказ S3 —
 * разные события, и «загрузка не удалась» на оба уводит в неверную сторону.
 */
export function putWithProgress(
  url: string,
  file: File,
  onProgress: (sent: number, total: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url, true);
    xhr.setRequestHeader("Content-Type", file.type);

    xhr.upload.onprogress = (e) => {
      // lengthComputable ложно, когда размер неизвестен — тогда сообщаем ноль
      // как «неизвестно», а не как «ничего не ушло»: см. uploadPercent.
      onProgress(e.loaded, e.lengthComputable ? e.total : 0);
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`заливка в S3 вернула ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error("соединение с хранилищем оборвалось"));
    xhr.ontimeout = () => reject(new Error("хранилище не ответило вовремя"));
    xhr.onabort = () => reject(new Error("загрузка отменена"));

    xhr.send(file);
  });
}
