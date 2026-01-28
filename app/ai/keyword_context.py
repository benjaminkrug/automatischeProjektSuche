"""A2: LLM-basierte Kontext-Analyse für Keywords.

Unterscheidet ob Keywords tatsächlich als Anforderung gesucht werden
oder nur beiläufig erwähnt werden.

Beispiel:
- "Wir testen mit Python" -> Python ist "mentioned" (nur erwähnt)
- "Wir suchen Python-Entwickler" -> Python ist "required" (gesucht)

Usage:
    from app.ai.keyword_context import analyze_keyword_context

    result = analyze_keyword_context(
        "Wir suchen einen Vue-Entwickler. Python nutzen wir intern.",
        ["vue", "python"]
    )
    # result: {"vue": "required", "python": "mentioned"}
"""

import json
from typing import Dict, List, Optional

from openai import OpenAI

from app.core.logging import get_logger
from app.settings import settings

logger = get_logger("ai.keyword_context")


# Prompt template for keyword context analysis
CONTEXT_PROMPT = """Analysiere ob die folgenden Keywords im Projekttext als GESUCHT oder nur ERWÄHNT werden.

Projekttext:
{text}

Keywords: {keywords}

Regeln:
- "required" = Das Keyword beschreibt eine gesuchte Fähigkeit/Technologie für die Stelle
- "mentioned" = Das Keyword wird nur erwähnt (z.B. "wir nutzen intern", "testen mit", "Schnittstelle zu")
- "unclear" = Nicht eindeutig erkennbar

Antworte NUR im JSON-Format:
{{
  "keyword1": "required",
  "keyword2": "mentioned",
  ...
}}

Nur valides JSON, kein zusätzlicher Text."""


def analyze_keyword_context(
    text: str,
    keywords: List[str],
    max_text_length: int = 2000,
    max_keywords: int = 10,
) -> Dict[str, str]:
    """Analysiere ob Keywords gesucht oder nur erwähnt werden.

    Verwendet GPT-4o-mini für kostengünstige Kontextanalyse.

    Args:
        text: Projektbeschreibung
        keywords: Liste der zu prüfenden Keywords
        max_text_length: Maximale Textlänge (truncation)
        max_keywords: Maximale Anzahl Keywords pro Anfrage

    Returns:
        Dict mapping keyword to "required" | "mentioned" | "unclear"

    Raises:
        ValueError: If keywords list is empty
    """
    if not keywords:
        return {}

    # Truncate inputs for cost control
    truncated_text = text[:max_text_length]
    limited_keywords = keywords[:max_keywords]

    logger.debug(
        "Analyzing context for %d keywords (text: %d chars)",
        len(limited_keywords),
        len(truncated_text),
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key)

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Cost-effective model
            messages=[
                {
                    "role": "user",
                    "content": CONTEXT_PROMPT.format(
                        text=truncated_text,
                        keywords=", ".join(limited_keywords),
                    ),
                }
            ],
            temperature=0,  # Deterministic output
            max_tokens=200,  # Limit output size
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        result = json.loads(content)

        # Normalize keys to lowercase and validate values
        normalized = {}
        for kw in limited_keywords:
            kw_lower = kw.lower()
            # Try exact match first, then lowercase
            value = result.get(kw) or result.get(kw_lower) or "unclear"
            if value not in ("required", "mentioned", "unclear"):
                value = "unclear"
            normalized[kw_lower] = value

        logger.debug("Context analysis result: %s", normalized)
        return normalized

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse LLM response as JSON: %s", e)
        return {kw.lower(): "unclear" for kw in limited_keywords}

    except Exception as e:
        logger.error("Error in keyword context analysis: %s", e)
        return {kw.lower(): "unclear" for kw in limited_keywords}


def calculate_context_adjusted_score(
    tier_1_keywords: List[str],
    tier_2_keywords: List[str],
    text: str,
    base_tier_1_score: int,
    base_tier_2_score: int,
    use_llm: bool = True,
) -> tuple[int, int, Dict[str, str]]:
    """Berechne kontext-adjustierten Keyword-Score.

    Reduziert den Score für Keywords die nur "mentioned" sind.

    Args:
        tier_1_keywords: Liste der Tier-1 Keywords
        tier_2_keywords: Liste der Tier-2 Keywords
        text: Projektbeschreibung
        base_tier_1_score: Basis-Score für Tier 1
        base_tier_2_score: Basis-Score für Tier 2
        use_llm: Ob LLM für Kontext-Analyse verwendet werden soll

    Returns:
        Tuple of (adjusted_tier_1_score, adjusted_tier_2_score, context_dict)
    """
    if not use_llm:
        return base_tier_1_score, base_tier_2_score, {}

    # Only analyze Tier-1 keywords for cost control
    all_keywords = tier_1_keywords[:5]  # Max 5 Tier-1 keywords

    if not all_keywords:
        return base_tier_1_score, base_tier_2_score, {}

    context = analyze_keyword_context(text, all_keywords)

    # Calculate penalty for "mentioned" keywords
    mentioned_tier_1 = sum(
        1 for kw in tier_1_keywords if context.get(kw.lower()) == "mentioned"
    )

    # Penalty: -10 points per mentioned Tier-1 keyword
    tier_1_penalty = mentioned_tier_1 * 10
    adjusted_tier_1 = max(0, base_tier_1_score - tier_1_penalty)

    if mentioned_tier_1 > 0:
        logger.info(
            "Context adjustment: %d Tier-1 keywords only mentioned -> -%.0d points",
            mentioned_tier_1,
            tier_1_penalty,
        )

    return adjusted_tier_1, base_tier_2_score, context


def is_keyword_required(keyword: str, text: str) -> bool:
    """Prüfe ob ein einzelnes Keyword tatsächlich gesucht wird.

    Convenience-Funktion für einzelne Keywords.

    Args:
        keyword: Das zu prüfende Keyword
        text: Projektbeschreibung

    Returns:
        True wenn das Keyword als Anforderung gesucht wird
    """
    result = analyze_keyword_context(text, [keyword])
    return result.get(keyword.lower()) == "required"


# Cost estimation
# GPT-4o-mini: $0.15/1M input tokens, $0.60/1M output tokens
# Average request: ~500 input tokens, ~50 output tokens
# Cost per request: ~$0.0001 (0.01 cent)
# 100 projects/day * 30 days = ~$0.30/month
