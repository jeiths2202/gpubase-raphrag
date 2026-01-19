"""
Reliability Service
출처 신뢰도 계산 서비스

Calculates reliability scores for search results based on:
1. Source count: Number of unique sources
2. Average similarity: Mean similarity score
3. Source diversity: Ratio of unique documents to total chunks
4. Source quality: Quality weight based on source type
"""
from typing import Dict, List, Any
from ..models.query import ReliabilityLevel, SourceReliability
from ..core.config import api_settings


# Source type quality weights
SOURCE_QUALITY_WEIGHTS = {
    "global_kb": 1.0,      # Admin-uploaded knowledge base
    "vector": 1.0,         # Vector search from KB
    "graph": 0.9,          # Graph-based results
    "session": 0.6,        # User session documents
    "external": 0.8,       # External resources (Notion, etc.)
    "external_notion": 0.8,
    "external_github": 0.85,
    "external_confluence": 0.85,
    "file_context": 0.5,   # Attached file context
}


def calculate_source_count_score(source_count: int) -> float:
    """
    Calculate score based on number of sources
    1개 = 0.3, 2개 = 0.6, 3개+ = 1.0
    """
    if source_count <= 0:
        return 0.0
    if source_count == 1:
        return 0.3
    if source_count == 2:
        return 0.6
    return 1.0


def calculate_avg_similarity(sources: List[Dict[str, Any]]) -> float:
    """Calculate average similarity score from sources"""
    if not sources:
        return 0.0

    scores = []
    for source in sources:
        # Try different score field names
        score = source.get("score") or source.get("similarity") or source.get("result_score")
        if score is not None:
            scores.append(float(score))

    if not scores:
        return 0.5  # Default to medium if no scores

    return sum(scores) / len(scores)


def calculate_source_diversity(sources: List[Dict[str, Any]]) -> float:
    """
    Calculate source diversity (unique documents / total sources)
    Higher diversity = more reliable (multiple perspectives)
    """
    if not sources:
        return 0.0

    # Extract unique document IDs
    doc_ids = set()
    for source in sources:
        doc_id = (
            source.get("doc_id") or
            source.get("document_id") or
            source.get("source", {}).get("doc_id") if isinstance(source.get("source"), dict) else None
        )
        if doc_id:
            doc_ids.add(doc_id)

    if not doc_ids:
        return 0.5  # Default if no doc IDs found

    # Calculate diversity ratio
    diversity = len(doc_ids) / len(sources)
    # Normalize: 0.2+ unique ratio = 1.0, below that scales down
    return min(1.0, diversity * 2.5)


def calculate_source_quality(sources: List[Dict[str, Any]]) -> float:
    """Calculate weighted quality score based on source types"""
    if not sources:
        return 0.0

    total_weight = 0.0
    for source in sources:
        source_type = source.get("source_type", "vector")
        weight = SOURCE_QUALITY_WEIGHTS.get(source_type, 0.7)
        total_weight += weight

    return total_weight / len(sources)


def get_reliability_level(score: float) -> ReliabilityLevel:
    """Determine reliability level from score"""
    high_threshold = getattr(api_settings, 'RELIABILITY_HIGH_THRESHOLD', 0.7)
    medium_threshold = getattr(api_settings, 'RELIABILITY_MEDIUM_THRESHOLD', 0.4)

    if score >= high_threshold:
        return ReliabilityLevel.HIGH
    if score >= medium_threshold:
        return ReliabilityLevel.MEDIUM
    return ReliabilityLevel.LOW


def generate_explanation(
    level: ReliabilityLevel,
    factors: Dict[str, float],
    source_count: int,
    language: str = "ko"
) -> str:
    """
    Generate user-friendly explanation
    Supports Korean, English, Japanese
    """
    explanations = {
        "ko": {
            ReliabilityLevel.HIGH: f"{source_count}개의 출처에서 일관된 정보를 찾았습니다. 신뢰도가 높습니다.",
            ReliabilityLevel.MEDIUM: f"{source_count}개의 출처에서 정보를 찾았습니다. 추가 확인을 권장합니다.",
            ReliabilityLevel.LOW: "관련 출처가 적거나 일관성이 낮습니다. 추가 검색을 권장합니다.",
        },
        "en": {
            ReliabilityLevel.HIGH: f"Consistent information found from {source_count} sources. High reliability.",
            ReliabilityLevel.MEDIUM: f"Information found from {source_count} sources. Additional verification recommended.",
            ReliabilityLevel.LOW: "Limited sources or low consistency. Additional search recommended.",
        },
        "ja": {
            ReliabilityLevel.HIGH: f"{source_count}件のソースから一貫した情報が見つかりました。信頼性が高いです。",
            ReliabilityLevel.MEDIUM: f"{source_count}件のソースから情報が見つかりました。追加確認を推奨します。",
            ReliabilityLevel.LOW: "関連ソースが少ないか、一貫性が低いです。追加検索を推奨します。",
        }
    }

    lang_key = language if language in explanations else "ko"
    return explanations[lang_key].get(level, explanations["ko"][level])


def calculate_reliability(
    sources: List[Dict[str, Any]],
    language: str = "ko"
) -> SourceReliability:
    """
    Calculate overall reliability score for search sources

    Args:
        sources: List of source dictionaries from search results
        language: Response language for explanation

    Returns:
        SourceReliability with score, level, factors, and explanation
    """
    if not sources:
        return SourceReliability(
            score=0.0,
            level=ReliabilityLevel.LOW,
            factors={
                "source_count": 0.0,
                "avg_similarity": 0.0,
                "source_diversity": 0.0,
                "source_quality": 0.0
            },
            explanation=generate_explanation(ReliabilityLevel.LOW, {}, 0, language)
        )

    # Calculate individual factors
    source_count = len(sources)
    source_count_score = calculate_source_count_score(source_count)
    avg_similarity = calculate_avg_similarity(sources)
    source_diversity = calculate_source_diversity(sources)
    source_quality = calculate_source_quality(sources)

    # Weighted combination (weights sum to 1.0)
    weights = {
        "source_count": 0.25,
        "avg_similarity": 0.35,
        "source_diversity": 0.15,
        "source_quality": 0.25
    }

    factors = {
        "source_count": round(source_count_score, 3),
        "avg_similarity": round(avg_similarity, 3),
        "source_diversity": round(source_diversity, 3),
        "source_quality": round(source_quality, 3)
    }

    # Calculate overall score
    overall_score = (
        source_count_score * weights["source_count"] +
        avg_similarity * weights["avg_similarity"] +
        source_diversity * weights["source_diversity"] +
        source_quality * weights["source_quality"]
    )
    overall_score = round(min(1.0, max(0.0, overall_score)), 3)

    # Determine level
    level = get_reliability_level(overall_score)

    # Generate explanation
    explanation = generate_explanation(level, factors, source_count, language)

    return SourceReliability(
        score=overall_score,
        level=level,
        factors=factors,
        explanation=explanation
    )
