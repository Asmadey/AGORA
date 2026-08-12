"""
Сборка отчёта — задача #20, часть синтеза.

Числа приходят из `aggregate.py` готовыми. Здесь модель делает то, чего код не
умеет: называет темы, разногласия и связывает наблюдения в текст.

─── Утверждение без опоры не проходит ────────────────────────────────────────
Приёмка требует, чтобы каждое утверждение синтеза имело ссылку на таймкод или
цитату. Оставить это пунктом промпта нельзя: промпт — просьба, и требование,
которое только просят, выполняется через раз, причём незаметно. Абзац
«аудитория в целом настроена положительно» выглядит как вывод и не опирается
ни на что; отличить его от вывода с опорой читатель отчёта не обязан.

Поэтому отсев делает код: утверждение без таймкода и без кавычек с цитатой в
отчёт не попадает, а число отсеянных пишется в `degraded`. Пустой нарратив при
непустом агрегате — честный результат: он означает, что модель не сослалась ни
на что, и это стоит увидеть.

─── Дисклеймер не украшение ──────────────────────────────────────────────────
«Требует экспертной проверки» (Decision Log #8, #10) стоит в отчёте всегда и не
зависит от того, насколько хорош прогон. Синтетическая фокус-группа — это
гипотезы об аудитории, а не измерение аудитории, и отчёт без этой строки читают
как второе.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from .aggregate import aggregate, retention_risk_points, surviving

#: Дисклеймер из Decision Log #8/#10. Константа, а не текст в промпте: модель
#: не должна иметь возможности его не написать или переформулировать мягче.
DISCLAIMER = (
    "Результат синтетической фокус-группы — гипотезы об аудитории, а не измерение "
    "аудитории. Требует экспертной проверки перед принятием решений."
)

REQUEST_TIMEOUT_SEC = 180

ANALYST_ROLE = (
    "Ты — аналитик синтетической фокус-группы. Числа тебе даны посчитанными и "
    "пересчитывать их не нужно. Возвращай только JSON."
)

#: Что считается опорой утверждения: таймкод либо цитата в кавычках. Ёлочки и
#: обычные кавычки — обе формы: модель пишет то так, то так, и требовать одну
#: значило бы отсеивать за типографику.
_TIMECODE = re.compile(r"(?<![\d:])\d{1,2}:[0-5]\d(?::[0-5]\d)?(?![\d:])")
_QUOTE = re.compile(r"[«\"'][^«»\"']{8,}[»\"']")

_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$")


class AnalystClient(Protocol):
    def complete(self, *, system: str, user: str) -> str: ...


class QwenAnalystClient:
    """Боевой клиент аналитика: тот же endpoint, что у респондентов (#18)."""

    def __init__(self, config: Any | None = None, temperature: float = 0.3):
        from ..config import ModelConfig

        self.config = config or ModelConfig.from_env()
        # Ниже, чем у персон (0.9), и выше, чем у судьи (0.0). Нарратив должен
        # читаться как текст, а не как протокол, но два прогона по одному
        # набору не должны давать разные выводы.
        self.temperature = temperature

    def complete(self, *, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            default_headers=self.config.default_headers,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response = client.chat.completions.create(
            model=self.config.text_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            # Размышление выключено: см. ModelConfig.thinking — замер и причина.
            extra_body=self.config.extra_body(),
        )
        return (response.choices[0].message.content or "").strip()


def has_support(statement: str) -> bool:
    """Есть ли у утверждения опора: таймкод или цитата."""
    text = str(statement or "")
    return bool(_TIMECODE.search(text) or _QUOTE.search(text))


def build_report(
    *,
    answers: list[dict[str, Any]],
    pack: dict[str, Any],
    survey: dict[str, Any] | None = None,
    qa_flags: list[dict[str, Any]] | None = None,
    model: AnalystClient | None = None,
    template: str | None = None,
    replication_count: int = 1,
    artifact_path: Path | None = None,
    personas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Отчёт: посчитанный агрегат, точки риска и отсеянный по опорам синтез."""
    degraded: list[str] = []
    agg = aggregate(
        answers,
        survey=survey,
        qa_flags=qa_flags,
        replication_count=replication_count,
        # Запасной источник посегментного среза для ответов, где его нет.
        # Записанный в карточку срез главнее: он описывает ту аудиторию, на
        # которой отчёт посчитан, а реестр персон — сегодняшнюю.
        personas=personas,
    )
    kept = surviving(list(answers), qa_flags)

    report: dict[str, Any] = {
        "aggregate": agg,
        "retention_risk_points": retention_risk_points(
            answers, pack=pack, qa_flags=qa_flags
        ),
        "based_on_answers": len(kept),
        "excluded_by_qa": agg.get("excluded_by_qa", 0),
        "narrative": [],
        "themes": [],
        "disagreements": [],
        "strengths": [],
        "weaknesses": [],
        "disclaimer": DISCLAIMER,
        "degraded": degraded,
    }

    if model is None:
        degraded.append(
            "нарратив не собран: модель недоступна. Числовая часть отчёта посчитана "
            "полностью — она не зависит от модели"
        )
        _write(artifact_path, report)
        return report

    if template is None:
        template = _load_template()
    if not template:
        degraded.append("нарратив не собран: шаблон analytics.report пуст")
        _write(artifact_path, report)
        return report

    try:
        raw = model.complete(system=ANALYST_ROLE, user=_render(template, {
            "aggregate": agg,
            "retention_risk_points": report["retention_risk_points"],
            "all_persona_answers": [_body(a) for a in kept],
            "survey": survey or {},
            "content_title": pack.get("title", "материал"),
            "qa_flags": qa_flags or [],
        }))
        synthesis = _parse(raw)
    except Exception as exc:  # noqa: BLE001
        degraded.append(f"нарратив не собран: {type(exc).__name__}: {exc}")
        _write(artifact_path, report)
        return report

    for field in ("themes", "disagreements", "strengths", "weaknesses"):
        value = synthesis.get(field)
        if isinstance(value, list):
            report[field] = value

    narrative = [str(s) for s in (synthesis.get("narrative") or []) if str(s).strip()]
    supported = [s for s in narrative if has_support(s)]
    if len(supported) < len(narrative):
        degraded.append(
            f"из нарратива отсеяно утверждений без опоры на таймкод или цитату: "
            f"{len(narrative) - len(supported)} из {len(narrative)}"
        )
    report["narrative"] = supported

    _write(artifact_path, report)
    return report


def _body(item: dict[str, Any]) -> dict[str, Any]:
    inner = item.get("answer")
    return inner if isinstance(inner, dict) else item


def _load_template() -> str:
    here = Path(__file__).resolve()
    for parent in here.parents[:6]:
        candidate = parent / "prompts" / "analytics.report.md"
        if candidate.exists():
            return candidate.read_text("utf-8")
    return ""


def _render(template: str, variables: dict[str, Any]) -> str:
    out = template
    for name, value in variables.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        out = out.replace("{{" + name + "}}", text)
    return out


def _parse(text: str) -> dict[str, Any]:
    body = _FENCE.sub("", (text or "").strip())
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("ответ аналитика не является объектом")
    return parsed


def _write(path: Path | None, report: dict[str, Any]) -> None:
    if path is None:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
