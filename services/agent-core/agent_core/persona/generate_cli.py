"""
Точка входа генератора персон для веб-слоя (задача #9).

Веб зовёт генератор подпроцессом — тем же способом, что дистилляцию портретов в
#24. Логика генерации принадлежит воркеру, веб её только оркеструет: дублировать
методологию PRD §10 на TypeScript значило бы завести вторую реализацию
заземления, которая разойдётся с первой незаметно.

Конфигурация приходит одной JSON-строкой, а не набором флагов. Критериев шесть
и они списочные; разбирать `--age-group 25-34 --age-group 35-44` в оболочке —
лишний способ ошибиться на экранировании, а JSON уже есть готовым на стороне
вызывающего (apps/web/lib/audience.ts, toGenerationConfig).

Вывод — JSON в stdout, ошибки — текстом в stderr с ненулевым кодом возврата.
Маршрут отличает отказ по критериям от поломки развёртывания по тексту, поэтому
сообщение ValueError из restrict() должно доезжать до stderr дословно.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .generator import GenerationConfig, PersonaGenerator

#: Поля, которые принимаются из JSON. Всё остальное игнорируется молча:
#: вызывающий может положить в снимок конфигурации больше, чем нужно генератору.
ALLOWED = {
    "size", "seed", "serial", "city", "segment", "use_llm",
    "age_groups", "geos", "genders", "education",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Генерация персон по критериям (#9)")
    parser.add_argument("--config", required=True, help="JSON с полями GenerationConfig")
    parser.add_argument("--corpus", default=None, help="путь к корпусу (по умолчанию канонический)")
    args = parser.parse_args(argv)

    try:
        raw = json.loads(args.config)
    except json.JSONDecodeError as e:
        print(f"--config не является корректным JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print("--config должен быть объектом", file=sys.stderr)
        return 2

    config = GenerationConfig(**{k: v for k, v in raw.items() if k in ALLOWED})

    try:
        gen = PersonaGenerator.from_corpus(Path(args.corpus) if args.corpus else None)
        personas = gen.generate(config)
    except ValueError as e:
        # Отказ по критериям. Текст обязан дойти до пользователя целиком: в нём
        # написано, какой критерий пуст и что есть в корпусе.
        print(str(e), file=sys.stderr)
        return 1

    json.dump({"personas": personas}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
