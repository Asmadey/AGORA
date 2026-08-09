"""
LLM-as-judge для QA — задача #19.

Шов между прогоном и провайдером и разбор того, что судья вернул. Решений о
том, кого судить и что делать с вердиктом, здесь нет: они в `run.py`.

─── Почему confidence разбирается строго ─────────────────────────────────────
Отсутствующий `confidence` не подменяется единицей. Соблазн понятен: поле
необязательно у модели, а вердикт без него неудобен. Но единица означает
«судья уверен», то есть ровно противоположное тому, что произошло: судья про
уверенность промолчал. При включённой эскалации такой вердикт не был бы
перепроверен — то есть молчание модели закрывало бы ответ вместо суждения.

Поэтому пропущенный или нечисловой `confidence` даёт 0.0 и причину в вердикте.
Ноль отправит ответ на перепроверку, если она включена, и будет видно в
артефакте, если нет.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

#: Таймаут одного суждения. Судья читает один ответ и возвращает короткий JSON —
#: заметно быстрее, чем персона пишет свой ответ (там 120 с).
REQUEST_TIMEOUT_SEC = 60

#: Роль судьи. Одна строка, и она намеренно не содержит инструкций о том, ЧТО
#: проверять: всё содержательное живёт в промптах qa.* и правится в Промпт-студии
#: без выкладки. Здесь только то, что одинаково для всех трёх судей и не имеет
#: смысла как отдельная редактируемая единица.
JUDGE_ROLE = (
    "Ты — независимый верификатор ответов синтетических респондентов. "
    "Ты не участник опроса и не адвокат ответа. Возвращай только JSON."
)

_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$")


class JudgeClient(Protocol):
    """Тот же шов, что у RespondentClient (#18): system и user раздельно."""

    def complete(self, *, system: str, user: str) -> str: ...


class QwenJudgeClient:
    """Боевой судья: OpenAI-совместимый endpoint TimeWeb (Decision Log #1)."""

    def __init__(self, config: Any | None = None, base_url: str | None = None,
                 temperature: float = 0.0):
        from ..config import ModelConfig

        self.config = config or ModelConfig.from_env()
        self.base_url = base_url or self.config.base_url
        # Ноль, в отличие от 0.9 у респондента (#18). Там высокая температура —
        # условие метрики: персоны обязаны отличаться друг от друга. Здесь
        # наоборот: два прогона QA по одному ответу должны давать один вердикт,
        # иначе «ответ забракован» перестаёт быть свойством ответа.
        self.temperature = temperature

    def complete(self, *, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.base_url,
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
        )
        return (response.choices[0].message.content or "").strip()


def escalation_client(policy: Any, config: Any | None = None) -> QwenJudgeClient:
    """Судья-перепроверщик: тот же клиент, другой агент, то есть другая модель."""
    from ..config import ModelConfig

    cfg = config or ModelConfig.from_env()
    return QwenJudgeClient(config=cfg, base_url=policy.escalation_base_url(cfg.base_url))


# ─── Промпты ─────────────────────────────────────────────────────────────────


def find_prompt(name: str) -> Path:
    """Ищет промпт по раскладкам репозитория и образа — см. respondent/run.py."""
    here = Path(__file__).resolve()
    for parent in here.parents[:6]:
        candidate = parent / "prompts" / f"{name}.md"
        if candidate.exists():
            return candidate
    return here.parents[4] / "prompts" / f"{name}.md"


def load_templates() -> dict[str, str]:
    """Шаблоны из файлов. Прогон в конвейере передаёт снимок вместо этого."""
    out: dict[str, str] = {}
    for key in ("qa.consistency", "qa.grounding", "qa.diversity"):
        path = find_prompt(key)
        out[key] = path.read_text("utf-8") if path.exists() else ""
    return out


def render(template: str, variables: dict[str, Any]) -> str:
    """
    Подстановка `{{имя}}`.

    Значения сериализуются в JSON, а не приводятся к str: `str(dict)` дал бы
    питоновский repr с одинарными кавычками, а судья читает его как JSON и на
    половине ответов спотыкается о кавычки, а не о существо.
    """
    out = template
    for name, value in variables.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        out = out.replace("{{" + name + "}}", text)
    return out


# ─── Разбор вердикта ─────────────────────────────────────────────────────────


@dataclass
class JudgeVerdict:
    """Что судья сказал, приведённое к одной форме для всех трёх промптов."""

    verdict: str
    confidence: float
    reasons: list[str]


def parse_verdict(text: str) -> JudgeVerdict:
    """
    Приводит ответ судьи к общей форме.

    Три промпта возвращают разные поля: consistency — `consistency_score` и
    `flags`, grounding — `grounded` и `hallucinations`, diversity — `collapsed`
    и `note`. Общего у них ровно два: `verdict` и `confidence`. Остальное
    сводится здесь, чтобы `run.py` не знал, какой именно судья отвечал.

    Отсутствующий `verdict` выводится из профильного поля, а не считается «ok»:
    модель, вернувшая `grounded: false` без вердикта, сказала о дефекте.
    """
    body = _FENCE.sub("", (text or "").strip())
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("ответ судьи не является объектом")

    reasons: list[str] = []
    for key in ("flags", "hallucinations"):
        value = parsed.get(key)
        if isinstance(value, list):
            reasons.extend(str(v) for v in value if str(v).strip())
    note = parsed.get("note")
    if isinstance(note, str) and note.strip():
        reasons.append(note.strip())

    verdict = str(parsed.get("verdict") or "").strip().lower()
    if verdict not in ("ok", "regenerate"):
        # Профильные поля важнее отсутствующего вердикта: явное «не заземлён»
        # или «схлопнулось» — это и есть вердикт, просто названный иначе.
        bad = parsed.get("grounded") is False or parsed.get("collapsed") is True
        score = parsed.get("consistency_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            bad = bad or score < 7
        verdict = "regenerate" if bad else "ok"

    raw_conf = parsed.get("confidence")
    if isinstance(raw_conf, (int, float)) and not isinstance(raw_conf, bool):
        confidence = max(0.0, min(1.0, float(raw_conf)))
    else:
        confidence = 0.0
        reasons.append("судья не вернул confidence — вердикт принят как неуверенный")

    return JudgeVerdict(verdict=verdict, confidence=confidence, reasons=reasons)
