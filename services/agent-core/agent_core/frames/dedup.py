"""
Дедупликация кадров по перцептивному хешу (задача #16).

─── Почему не сравнение байтов ────────────────────────────────────────────
Два кадра неподвижной сцены практически никогда не совпадают побайтово: шум
кодека меняет отдельные пиксели, а JPEG перекодирует каждый кадр по-своему.
Побайтовое сравнение не выбросило бы ни одного кадра и при этом выглядело бы
работающей дедупликацией — самый дорогой вид дефекта, потому что он не
проявляется как отказ, а только как счёт за вызовы VLM.

─── Почему dHash, а не среднее ────────────────────────────────────────────
dHash кодирует ГРАДИЕНТЫ: каждый бит — ответ на вопрос «этот пиксель светлее
соседа справа». Общая яркость из результата уходит, поэтому плавное затемнение
или смена экспозиции внутри одной статичной сцены не считаются новым кадром, а
перемещение объекта — считается. aHash (сравнение со средним) на том же
затемнении дал бы другой хеш и оставил бы оба кадра.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..media.errors import MediaError
from ..media.probe import _tool

#: Сетка dHash: 9 столбцов дают 8 сравнений в строке, 8 строк — итого 64 бита.
HASH_WIDTH = 9
HASH_HEIGHT = 8

#: Максимальное расстояние Хэмминга, при котором кадры считаются одинаковыми.
#:
#: 4 бита из 64 — примерно 6% различий. Порог подобран под задачу «убрать
#: повторы внутри сцены», а не «найти одинаковые картинки»: ошибиться в сторону
#: сохранения лишнего кадра стоит одного вызова VLM, а в сторону выброса —
#: потерянного куска смысла, который уже ничем не восстановить.
DEFAULT_THRESHOLD = 4

FFMPEG_TIMEOUT = 120


def dhash(image: str | Path) -> int:
    """
    64-битный перцептивный хеш кадра.

    Уменьшение до 9×8 в оттенках серого делает ffmpeg — ставить Pillow ради
    одного resize незачем, а ffmpeg в контуре уже обязателен.
    """
    proc = subprocess.run(
        [_tool("ffmpeg"), "-v", "error", "-i", str(image),
         "-vf", f"scale={HASH_WIDTH}:{HASH_HEIGHT}:flags=area,format=gray",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, timeout=FFMPEG_TIMEOUT,
    )
    pixels = proc.stdout
    expected = HASH_WIDTH * HASH_HEIGHT
    if len(pixels) < expected:
        raise MediaError(
            f"не удалось прочитать кадр {Path(image).name} для хеширования: "
            f"{(proc.stderr or b'').decode('utf-8', 'replace').strip()[-160:] or 'пустой вывод'}"
        )

    bits = 0
    for row in range(HASH_HEIGHT):
        base = row * HASH_WIDTH
        for col in range(HASH_WIDTH - 1):
            bits = (bits << 1) | int(pixels[base + col] > pixels[base + col + 1])
    return bits


def hamming(a: int, b: int) -> int:
    """Число различающихся битов — мера непохожести двух кадров."""
    return (a ^ b).bit_count()


def dedupe(
    frames: list[Path],
    threshold: int = DEFAULT_THRESHOLD,
) -> list[Path]:
    """
    Оставляет по одному кадру на каждую визуально различимую картинку.

    Сравнение идёт с УЖЕ ОСТАВЛЕННЫМИ кадрами, а не с непосредственно
    предыдущим. Цепочка попарно похожих кадров при плавном движении камеры
    иначе схлопнулась бы целиком: каждый следующий отличается от соседа на
    два бита, а от первого — на сорок, и при сравнении с соседом ни один из
    них не был бы признан новым.

    Порядок сохраняется: дальше по конвейеру он же порядок таймкодов.
    """
    kept: list[Path] = []
    hashes: list[int] = []

    for frame in frames:
        h = dhash(frame)
        if any(hamming(h, seen) <= threshold for seen in hashes):
            continue
        kept.append(frame)
        hashes.append(h)

    return kept
