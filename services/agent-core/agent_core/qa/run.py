"""
Прогон QA — задача #19.

Собирает два слоя в один вердикт на каждый ответ и один на выборку целиком.

─── Порядок слоёв ────────────────────────────────────────────────────────────
Сначала правила (`checks.py`), судья — только по тем ответам, где правила
ничего не нашли. Порядок не про экономию, хотя экономия и получается: обратный
порядок означал бы, что арифметически доказанный дефект — таймкод за пределами
ролика — можно замять мнением модели. Судья, сказавший «ok» на ответе с
07:45 при столетнем ролике, не прав; принимать его сторону не за что.

Из того же порядка следует, что ответ, забракованный правилом, судье не
отправляется ВООБЩЕ, а не только по забракованной проверке. Он уже помечен на
перегенерацию, и второе суждение о нём ничего не меняет — только стоит денег.

─── Разнообразие считается по выжившим ───────────────────────────────────────
Ответы, отправленные на перегенерацию, из выборки для diversity исключаются.
Иначе метрика меряет набор, которого не будет: половину этих ответов заменят,
и разброс станет другим. Здесь это заодно закрывает утечку — материал
забракованного ответа не уходит судье через промпт diversity, где лежит вся
выборка сразу.

─── Эскалация только для вердиктов судьи ─────────────────────────────────────
Вердикт правила не эскалируется никогда, какой бы confidence ему ни приписали:
у арифметики нет неуверенности, и перепроверять модель большего размера тут
нечего. Эскалация — механизм ровно для того случая, который описан в PRD §14.1:
дешёвая модель созналась в неуверенности.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..respondent.diversity import diversity_report
from .checks import consistency_reasons, grounding_reasons
from .judge import JUDGE_ROLE, JudgeClient, load_templates, parse_verdict, render

#: Минимальный размер выборки, на котором разнообразие вообще измеримо. Ниже
#: этого числа distinct-2 и дисперсия считаются по двум-трём наблюдениям и
#: говорят о случайности, а не о модели.
DIVERSITY_MIN_SAMPLE = 2

KIND_CONSISTENCY = "consistency"
KIND_GROUNDING = "grounding"
KIND_DIVERSITY = "diversity"


@dataclass
class QaOutcome:
    """Итог проверки. Вердикты все, флаги — только те, что требуют перегенерации."""

    verdicts: list[dict[str, Any]] = field(default_factory=list)
    diversity: dict[str, Any] = field(default_factory=dict)
    escalated: int = 0
    failures: int = 0
    failure_reasons: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)

    @property
    def flagged(self) -> list[dict[str, Any]]:
        return [v for v in self.verdicts if v.get("verdict") == "regenerate"]

    def summary(self) -> dict[str, Any]:
        """
        Сводка для экрана исследования.

        ─── Почему её приходится считать здесь ─────────────────────────────
        Наружу из прогона уходили только `flagged` — те вердикты, что требуют
        перегенерации. По ним видно, сколько ответов исключено, и не видно
        ничего больше: ни по каким видам проверки, ни кем забраковано (правило
        или судья), ни сколько вердиктов ушло на эскалацию. Полный список
        вердиктов живёт в `qa_report.json` в рабочем каталоге прогона, а он
        внутри контейнера и умирает вместе с ним.

        ─── Про перегенерацию, которой нет ─────────────────────────────────
        Забракованный ответ ИСКЛЮЧАЕТСЯ из агрегата, а не переспрашивается:
        механизма перегенерации в системе нет. Поэтому здесь нет и не может быть
        поля «сколько персон пересоздано» — писать в него ноль значило бы
        обещать несуществующий механизм, а не сообщать факт.
        """
        flagged = self.flagged
        by_kind: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for verdict in flagged:
            kind = str(verdict.get("kind") or "неизвестно")
            source = str(verdict.get("source") or "неизвестно")
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_source[source] = by_source.get(source, 0) + 1

        return {
            "checked": len(self.verdicts),
            "flagged": len(flagged),
            "by_kind": by_kind,
            "by_source": by_source,
            "escalated": self.escalated,
            # Отказы судьи: ответ, по которому судья не высказался, остаётся в
            # агрегате. Знать их число обязательно — иначе «проверено N» читается
            # как «N проверок прошло», а не «N попыток сделано».
            "judge_failures": self.failures,
            "degraded": list(self.degraded),
        }


def _verdict(
    kind: str,
    *,
    source: str,
    verdict: str,
    confidence: float,
    reasons: list[str],
    item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "persona_id": (item or {}).get("persona_id"),
        "persona_name": (item or {}).get("persona_name"),
        "replication": int((item or {}).get("replication") or 0) if item else None,
        "verdict": verdict,
        "confidence": float(confidence),
        "reasons": list(reasons),
        "source": source,
        "escalated": False,
    }


def _body(item: dict[str, Any]) -> dict[str, Any]:
    """Тело ответа: конверт прогона (#18) или голый ответ."""
    inner = item.get("answer")
    return inner if isinstance(inner, dict) else item


def run_qa(
    *,
    answers: list[dict[str, Any]],
    pack: dict[str, Any],
    personas: list[dict[str, Any]] | None = None,
    survey: dict[str, Any] | None = None,
    judge: JudgeClient | None = None,
    escalation_judge: JudgeClient | None = None,
    policy: Any | None = None,
    templates: dict[str, str] | None = None,
    artifact_path: Path | None = None,
) -> QaOutcome:
    """
    Проверяет набор ответов и возвращает вердикты.

    `policy` — QaConfig; None означает «эскалация выключена», а не «читать
    окружение». Умолчание намеренно тихое: узел конвейера передаёт политику
    явно, а вызов из теста или из скрипта не должен внезапно начать ходить во
    второго агента из-за переменной, оставшейся в окружении машины.
    """
    outcome = QaOutcome()
    # Копия входа: правила ничего не меняют, но судья и артефакт видят те же
    # словари, и одна неосторожная запись в них позже стала бы дефектом,
    # который виден только на втором прогоне.
    answers = copy.deepcopy(list(answers))
    dna_by_id = {
        str(p.get("id")): p.get("dna", {}) for p in (personas or []) if isinstance(p, dict)
    }
    tpl = templates if templates is not None else load_templates()

    if judge is None:
        outcome.degraded.append(
            "QA без судьи: проверены только детерминированные правила. Согласованность "
            "ответа с характером персоны и выдуманные детали внутри длительности ролика "
            "не проверялись"
        )

    # ── Слой правил ──────────────────────────────────────────────────────────
    clean: list[dict[str, Any]] = []
    for item in answers:
        body = _body(item)
        c_reasons = consistency_reasons(body, survey)
        g_reasons = grounding_reasons(body, pack)
        outcome.verdicts.append(_verdict(
            KIND_CONSISTENCY, source="rule",
            verdict="regenerate" if c_reasons else "ok",
            confidence=1.0, reasons=c_reasons, item=item,
        ))
        outcome.verdicts.append(_verdict(
            KIND_GROUNDING, source="rule",
            verdict="regenerate" if g_reasons else "ok",
            confidence=1.0, reasons=g_reasons, item=item,
        ))
        if not c_reasons and not g_reasons:
            clean.append(item)

    # ── Слой судьи ───────────────────────────────────────────────────────────
    if judge is not None:
        for item in clean:
            body = _body(item)
            dna = dna_by_id.get(str(item.get("persona_id")), {})
            _judge_into(
                outcome, judge, KIND_CONSISTENCY, item,
                tpl.get("qa.consistency", ""),
                {"persona_dna": dna, "persona_answer": body},
            )
            _judge_into(
                outcome, judge, KIND_GROUNDING, item,
                tpl.get("qa.grounding", ""),
                {"persona_answer": body, "video_understanding": pack},
            )

    # ── Разнообразие ─────────────────────────────────────────────────────────
    outcome.diversity = diversity_report(clean)
    if len(clean) < DIVERSITY_MIN_SAMPLE:
        outcome.verdicts.append(_verdict(
            KIND_DIVERSITY, source="rule", verdict="ok", confidence=1.0,
            reasons=[
                f"прошедших правила ответов {len(clean)} — разнообразие не измеримо "
                f"(нужно от {DIVERSITY_MIN_SAMPLE})"
            ],
        ))
    else:
        collapsed = bool(outcome.diversity.get("mode_collapse"))
        outcome.verdicts.append(_verdict(
            KIND_DIVERSITY, source="rule",
            verdict="regenerate" if collapsed else "ok", confidence=1.0,
            reasons=[
                f"distinct-2 {outcome.diversity.get('distinct_2')} при пороге "
                f"{outcome.diversity.get('distinct_2_threshold')}; дисперсия баллов "
                f"{outcome.diversity.get('score_stdev')} при пороге "
                f"{outcome.diversity.get('score_stdev_threshold')}"
            ] if collapsed else [],
        ))
        if judge is not None and not collapsed:
            _judge_into(
                outcome, judge, KIND_DIVERSITY, None,
                tpl.get("qa.diversity", ""),
                {
                    "all_persona_answers": [_body(i) for i in clean],
                    "expected_variance": outcome.diversity,
                },
            )

    # ── Эскалация ────────────────────────────────────────────────────────────
    if policy is not None and getattr(policy, "escalation_enabled", False):
        threshold = float(getattr(policy, "escalation_confidence", 0.0))
        big = escalation_judge
        for verdict in outcome.verdicts:
            if verdict["source"] != "judge" or verdict["confidence"] >= threshold:
                continue
            if big is None:
                from .judge import escalation_client

                big = escalation_client(policy)
            _escalate(outcome, big, verdict, tpl, answers, clean, pack, dna_by_id)

    if artifact_path is not None:
        _write_artifact(artifact_path, outcome, policy)

    return outcome


def _judge_into(
    outcome: QaOutcome,
    judge: JudgeClient,
    kind: str,
    item: dict[str, Any] | None,
    template: str,
    variables: dict[str, Any],
) -> None:
    """
    Спрашивает судью и ЗАМЕНЯЕТ вердикт правила по этому виду проверки.

    Отказ судьи не роняет прогон и не превращается в «ok»: вердикт правила
    остаётся на месте, а причина уходит в failure_reasons. Ронять прогон здесь
    значило бы терять оплаченные ответы персон из-за таймаута проверяющего.
    """
    if not template:
        outcome.failures += 1
        outcome.failure_reasons.append(f"{kind}: шаблон промпта пуст")
        return
    try:
        raw = judge.complete(system=JUDGE_ROLE, user=render(template, variables))
        parsed = parse_verdict(raw)
    except Exception as exc:  # noqa: BLE001
        outcome.failures += 1
        outcome.failure_reasons.append(
            f"{kind} {(item or {}).get('persona_id', 'выборка')}: {type(exc).__name__}: {exc}"
        )
        return

    fresh = _verdict(
        kind, source="judge", verdict=parsed.verdict,
        confidence=parsed.confidence, reasons=parsed.reasons, item=item,
    )
    _replace(outcome, fresh)


def _replace(outcome: QaOutcome, fresh: dict[str, Any]) -> None:
    """Ставит новый вердикт на место прежнего по (вид, персона, повтор)."""
    key = (fresh["kind"], fresh["persona_id"], fresh["replication"])
    for i, existing in enumerate(outcome.verdicts):
        if (existing["kind"], existing["persona_id"], existing["replication"]) == key:
            outcome.verdicts[i] = fresh
            return
    outcome.verdicts.append(fresh)


def _escalate(
    outcome: QaOutcome,
    big: JudgeClient,
    verdict: dict[str, Any],
    tpl: dict[str, str],
    answers: list[dict[str, Any]],
    clean: list[dict[str, Any]],
    pack: dict[str, Any],
    dna_by_id: dict[str, Any],
) -> None:
    """Перепроверяет один вердикт моделью большего размера."""
    kind = verdict["kind"]
    if kind == KIND_DIVERSITY:
        template = tpl.get("qa.diversity", "")
        variables: dict[str, Any] = {
            "all_persona_answers": [_body(i) for i in clean],
            "expected_variance": outcome.diversity,
        }
        item = None
    else:
        item = next(
            (
                a for a in answers
                if a.get("persona_id") == verdict["persona_id"]
                and int(a.get("replication") or 0) == verdict["replication"]
            ),
            None,
        )
        if item is None:
            return
        body = _body(item)
        if kind == KIND_CONSISTENCY:
            template = tpl.get("qa.consistency", "")
            variables = {
                "persona_dna": dna_by_id.get(str(item.get("persona_id")), {}),
                "persona_answer": body,
            }
        else:
            template = tpl.get("qa.grounding", "")
            variables = {"persona_answer": body, "video_understanding": pack}

    if not template:
        return
    try:
        raw = big.complete(system=JUDGE_ROLE, user=render(template, variables))
        parsed = parse_verdict(raw)
    except Exception as exc:  # noqa: BLE001
        outcome.failures += 1
        outcome.failure_reasons.append(
            f"эскалация {kind} {verdict['persona_id']}: {type(exc).__name__}: {exc}"
        )
        return

    fresh = _verdict(
        kind, source="escalated", verdict=parsed.verdict,
        confidence=parsed.confidence, reasons=parsed.reasons, item=item,
    )
    fresh["escalated"] = True
    fresh["escalated_from"] = {
        "verdict": verdict["verdict"], "confidence": verdict["confidence"],
    }
    _replace(outcome, fresh)
    outcome.escalated += 1


def _write_artifact(path: Path, outcome: QaOutcome, policy: Any | None) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "verdicts": outcome.verdicts,
                "flagged": outcome.flagged,
                "diversity": outcome.diversity,
                "escalated": outcome.escalated,
                # Порог кладётся в артефакт вместе с результатом: без него
                # число эскалаций нечем объяснить через месяц, когда переменная
                # окружения уже другая.
                "escalation_confidence": (
                    getattr(policy, "escalation_confidence", None) if policy else None
                ),
                "escalation_enabled": bool(
                    policy and getattr(policy, "escalation_enabled", False)
                ),
                "failures": outcome.failures,
                "failure_reasons": outcome.failure_reasons,
                "degraded": outcome.degraded,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
