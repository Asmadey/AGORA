"""
Auto-distillation of corpus into audience portrait .md (task #24).

Reads the grounding corpus (unified_respondent_sessions.json), groups records
by segment (age_group × geo × gender), and produces a structured .md portrait.

Two modes:
  1. Deterministic (default, no LLM): builds .md directly from corpus statistics
     — distributions, top values, verbatims. Always works, always grounded.
  2. LLM (optional): calls an OpenAI-compatible API with the portrait.distill
     prompt template for a richer narrative. Falls back to deterministic if the
     API is unavailable or OPENAI_API_KEY is not set.

The deterministic mode is the backbone: it guarantees a non-empty, grounded
portrait in any environment, which is what the CDD test checks.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CORPUS_PATH = REPO_ROOT / "data" / "grounding" / "unified_respondent_sessions.json"
DEFAULT_PROMPT_PATH = REPO_ROOT / "prompts" / "portrait.distill.md"

AGE_GROUPS = ["14-17", "18-24", "25-34", "35-44", "45-59", "60+"]
GEOS = ["столицы", "центры субъектов", "иные НП"]
GENDERS = ["муж", "жен"]


def load_corpus(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load the grounding corpus JSON."""
    p = Path(path) if path else DEFAULT_CORPUS_PATH
    if not p.exists():
        raise FileNotFoundError(f"corpus not found: {p}")
    return json.loads(p.read_text("utf-8"))


def load_prompt_template(path: str | Path | None = None) -> str:
    """Load the portrait.distill prompt template."""
    p = Path(path) if path else DEFAULT_PROMPT_PATH
    if not p.exists():
        raise FileNotFoundError(f"prompt template not found: {p}")
    return p.read_text("utf-8")


def group_by_segment(
    records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group records by segment key: 'age_group|geo|gender'.

    Returns a dict mapping segment key → list of records.
    Segments with fewer than 2 records are merged into a broader
    'age_group|geo|*' bucket to avoid thin segments.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        socio = r.get("socio_demographics", {})
        age = socio.get("age_group", "?")
        geo = socio.get("geo", "?")
        gender = socio.get("gender", "?")
        key = f"{age}|{geo}|{gender}"
        groups.setdefault(key, []).append(r)

    # Merge thin segments (< 3 records) into age|geo|* buckets
    merged: dict[str, list[dict[str, Any]]] = {}
    thin_keys: list[str] = []
    for key, recs in groups.items():
        if len(recs) < 3:
            thin_keys.append(key)
        else:
            merged[key] = recs

    for key in thin_keys:
        parts = key.split("|")
        bucket_key = f"{parts[0]}|{parts[1]}|*"
        merged.setdefault(bucket_key, [])
        merged[bucket_key].extend(groups[key])

    return merged


def _pct(n: int, total: int) -> str:
    """Percentage string."""
    if total == 0:
        return "0%"
    return f"{n / total * 100:.0f}%"


def _collect_verbatims(
    records: list[dict[str, Any]], max_n: int = 6
) -> list[str]:
    """Collect up to max_n verbatim quotes from focus_group_verbatims."""
    quotes: list[str] = []
    for r in records:
        for v in r.get("focus_group_verbatims", []):
            if isinstance(v, str) and len(v.strip()) > 20:
                quotes.append(v.strip())
            if len(quotes) >= max_n:
                return quotes
    return quotes


def _collect_qualitative(records: list[dict[str, Any]]) -> dict[str, Counter]:
    """Aggregate qualitative fields across records."""
    interest = Counter()
    emotions = Counter()
    retention = Counter()
    realism = Counter()
    comprehension = Counter()

    for r in records:
        pr = r.get("perception_and_retention", {})
        if isinstance(pr.get("interest_level"), str):
            interest[pr["interest_level"]] += 1
        if isinstance(pr.get("retention_intent"), str):
            retention[pr["retention_intent"]] += 1
        if isinstance(pr.get("realism_perception"), str):
            realism[pr["realism_perception"]] += 1
        if isinstance(pr.get("idea_comprehension"), str):
            comprehension[pr["idea_comprehension"]] += 1
        for e in pr.get("emotions_evoked", []):
            if isinstance(e, str):
                emotions[e] += 1

    return {
        "interest": interest,
        "emotions": emotions,
        "retention": retention,
        "realism": realism,
        "comprehension": comprehension,
    }


def _collect_scores(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Aggregate agora_core_scores: mean per criterion."""
    criteria = [
        "overall_impression",
        "plot",
        "acting",
        "music",
        "cinematography",
    ]
    sums: dict[str, float] = {c: 0.0 for c in criteria}
    counts: dict[str, int] = {c: 0 for c in criteria}

    for r in records:
        scores = r.get("agora_core_scores_1_to_10", {})
        for c in criteria:
            v = scores.get(c)
            if isinstance(v, (int, float)):
                sums[c] += v
                counts[c] += 1

    return {
        c: {"mean": round(sums[c] / counts[c], 1) if counts[c] else 0.0, "n": counts[c]}
        for c in criteria
    }


def _collect_values(records: list[dict[str, Any]]) -> Counter:
    """Aggregate psychographics values."""
    values = Counter()
    for r in records:
        pv = r.get("psychographics_and_values", {})
        for v in pv.get("important_values", []):
            if isinstance(v, str):
                values[v.strip()] += 1
    return values


def _segment_label(key: str) -> str:
    """Human-readable segment label from key."""
    parts = key.split("|")
    age = parts[0] if len(parts) > 0 else "?"
    geo = parts[1] if len(parts) > 1 else "?"
    gender = parts[2] if len(parts) > 2 else "?"
    gender_label = {"муж": "мужчины", "жен": "женщины", "*": "оба пола"}.get(
        gender, gender
    )
    return f"{age} / {geo} / {gender_label}"


def distill_portrait_deterministic(
    records: list[dict[str, Any]],
    segment_key: str,
) -> str:
    """Build a structured .md portrait from corpus statistics (no LLM).

    This is the grounding backbone: every section is derived from real data,
    not generated. The output follows the structure from portrait.distill.md:
    Мета, Соцдем-профиль, Ценности, Медиаповедение, Предпочтения контента,
    Язык и тон, Decision pattern, Реальные цитаты, Источник данных.
    """
    n = len(records)
    label = _segment_label(segment_key)

    # Socdem distribution
    genders = Counter(r.get("socio_demographics", {}).get("gender", "?") for r in records)
    ages = Counter(r.get("socio_demographics", {}).get("age_group", "?") for r in records)
    geos = Counter(r.get("socio_demographics", {}).get("geo", "?") for r in records)

    # Scores
    scores = _collect_scores(records)

    # Qualitative
    qual = _collect_qualitative(records)

    # Values
    values = _collect_values(records)

    # Verbatims
    verbatims = _collect_verbatims(records, max_n=6)

    lines: list[str] = []
    lines.append(f"# Портрет аудитории: {label}")
    lines.append("")
    lines.append("## Мета")
    lines.append(f"- Сегмент: {label}")
    lines.append(f"- Размер выборки: {n} записей")
    lines.append("- Источник: авто-дистилляция из корпуса (unified_respondent_sessions)")
    lines.append("")

    lines.append("## Соцдем-профиль")
    lines.append("### Пол")
    for g in GENDERS:
        if genders.get(g, 0) > 0:
            lines.append(f"- {g}: {_pct(genders[g], n)} ({genders[g]})")
    lines.append("### Возрастные группы")
    for a in AGE_GROUPS:
        if ages.get(a, 0) > 0:
            lines.append(f"- {a}: {_pct(ages[a], n)} ({ages[a]})")
    lines.append("### География")
    for g in GEOS:
        if geos.get(g, 0) > 0:
            lines.append(f"- {g}: {_pct(geos[g], n)} ({geos[g]})")
    lines.append("")

    lines.append("## Ценности (топ)")
    if values:
        for val, cnt in values.most_common(5):
            lines.append(f"- {val} ({cnt})")
    else:
        lines.append("- Данные о ценностях не представлены в корпусе")
    lines.append("")

    lines.append("## Медиаповедение")
    lines.append("### Восприятие и удержание")
    if qual["interest"]:
        lines.append("Уровень интереса:")
        for k, v in qual["interest"].most_common():
            lines.append(f"- {k}: {v}")
    if qual["retention"]:
        lines.append("Намерение просмотра:")
        for k, v in qual["retention"].most_common():
            lines.append(f"- {k}: {v}")
    if qual["realism"]:
        lines.append("Восприятие реалистичности:")
        for k, v in qual["realism"].most_common():
            lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Предпочтения контента")
    lines.append("### Оценки по критериям (1-10, среднее)")
    for crit, data in scores.items():
        if data["n"] > 0:
            label_c = crit.replace("_", " ").title()
            lines.append(f"- {label_c}: {data['mean']} (n={data['n']})")
    if qual["emotions"]:
        lines.append("### Эмоциональные реакции (топ)")
        for emo, cnt in qual["emotions"].most_common(5):
            lines.append(f"- {emo} ({cnt})")
    lines.append("")

    lines.append("## Язык и тон")
    if qual["comprehension"]:
        lines.append("Понимание идеи:")
        for k, v in qual["comprehension"].most_common():
            lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Decision pattern (как решают смотреть/бросить)")
    if qual["retention"]:
        top_retention = qual["retention"].most_common(1)[0]
        lines.append(
            f"Преобладающее намерение: {top_retention[0]} "
            f"({top_retention[1]} из {n})"
        )
    if qual["interest"]:
        top_interest = qual["interest"].most_common(1)[0]
        lines.append(
            f"Преобладающий интерес: {top_interest[0]} "
            f"({top_interest[1]} из {n})"
        )
    lines.append("")

    lines.append("## Реальные цитаты (verbatim из focus_group_verbatims)")
    if verbatims:
        for i, q in enumerate(verbatims, 1):
            # Truncate very long quotes
            display = q if len(q) <= 300 else q[:297] + "…"
            lines.append(f"{i}. > {display}")
    else:
        lines.append("Цитаты отсутствуют в этом сегменте.")
    lines.append("")

    lines.append("## Источник данных")
    lines.append(
        f"- Корпус: data/grounding/unified_respondent_sessions.json ({n} записей в сегменте)"
    )
    lines.append("- Промпт: prompts/portrait.distill.md")
    lines.append("- Метод: авто-дистилляция (детерминированная агрегация)")

    return "\n".join(lines)


def distill_portrait_llm(
    records: list[dict[str, Any]],
    segment_key: str,
    prompt_template: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> str | None:
    """Call LLM with portrait.distill prompt to generate .md portrait.

    Returns None if the API call fails (caller falls back to deterministic).
    """
    try:
        from openai import OpenAI
    except ImportError:
        return None

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None

    url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.timeweb.cloud/v1")
    mdl = model or os.environ.get("AI_MODEL", "qwen3.6")

    # Prepare segment records as compact JSON
    segment_records = json.dumps(records[:30], ensure_ascii=False, indent=2)
    segment_label = _segment_label(segment_key)

    # Substitute variables into template
    prompt = prompt_template.replace("{{segment}}", segment_label)
    prompt = prompt.replace("{{segment_records}}", segment_records)

    try:
        client = OpenAI(api_key=key, base_url=url)
        response = client.chat.completions.create(
            model=mdl,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if content and content.strip():
            return content.strip()
        return None
    except Exception:
        return None


def distill_portrait(
    records: list[dict[str, Any]],
    segment_key: str,
    prompt_template: str | None = None,
    use_llm: bool = True,
) -> str:
    """Distill a portrait .md for a segment.

    Tries LLM first (if use_llm=True and API key available), falls back to
    deterministic aggregation. Always returns non-empty .md.
    """
    if use_llm and prompt_template:
        llm_result = distill_portrait_llm(records, segment_key, prompt_template)
        if llm_result:
            return llm_result

    return distill_portrait_deterministic(records, segment_key)


def distill_all_segments(
    corpus_path: str | Path | None = None,
    prompt_path: str | Path | None = None,
    use_llm: bool = True,
) -> list[dict[str, str]]:
    """Distill portraits for all segments in the corpus.

    Returns list of dicts: {segment, name, body_md}.
    """
    records = load_corpus(corpus_path)
    template = None
    if use_llm:
        try:
            template = load_prompt_template(prompt_path)
        except FileNotFoundError:
            pass

    groups = group_by_segment(records)
    results: list[dict[str, str]] = []

    for segment_key, seg_records in sorted(groups.items()):
        if len(seg_records) < 2:
            continue
        body_md = distill_portrait(seg_records, segment_key, template, use_llm=use_llm)
        name = f"Портрет: {_segment_label(segment_key)}"
        results.append({
            "segment": segment_key,
            "name": name,
            "body_md": body_md,
        })

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Distill audience portraits from corpus")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM, use deterministic mode only")
    parser.add_argument("--json", action="store_true", help="Output results as JSON array")
    parser.add_argument("--corpus", type=str, default=None, help="Path to corpus JSON")
    parser.add_argument("--prompt", type=str, default=None, help="Path to prompt template")
    args = parser.parse_args()

    use_llm_flag = not args.no_llm
    portraits = distill_all_segments(
        corpus_path=args.corpus,
        prompt_path=args.prompt,
        use_llm=use_llm_flag,
    )

    if args.json:
        print(json.dumps(portraits, ensure_ascii=False))
    else:
        print(f"Distilled {len(portraits)} portraits")
        for p in portraits:
            print(f"\n{'=' * 60}")
            print(f"Segment: {p['segment']}")
            print(f"Name: {p['name']}")
            print(f"Body length: {len(p['body_md'])} chars")
            print(f"Preview:\n{p['body_md'][:200]}...")