"""
Query Clarification Service

Core business logic for detecting ambiguous terms in user queries
and managing user preferences for term clarification.

Phase 2 extensions:
- ML-based entity recommendation using embedding similarity
- Integration with EntityEmbeddingService for context-aware suggestions
"""
import logging
import re
from typing import Optional, List, Dict, Any

from ..infrastructure.postgres.ambiguous_term_repository import (
    PostgresAmbiguousTermRepository,
)
from ..infrastructure.postgres.user_term_preference_repository import (
    PostgresUserTermPreferenceRepository,
)
from ..models.clarification import (
    ClarificationCheckRequest,
    ClarificationCheckResponse,
    ClarificationApplyRequest,
    ClarificationApplyResponse,
    DetectedAmbiguousTerm,
    PossibleEntity,
    TermSelection,
    MLRecommendation,
)

logger = logging.getLogger(__name__)


class QueryClarificationService:
    """
    Service for query clarification.

    Provides:
    - Detection of ambiguous terms in user queries
    - User preference management for clarifications
    - Query resolution with selected/preferred entities
    - ML-based entity recommendations (Phase 2)
    """

    def __init__(
        self,
        ambiguous_term_repo: PostgresAmbiguousTermRepository,
        user_preference_repo: PostgresUserTermPreferenceRepository,
        entity_embedding_service: Optional[Any] = None,
    ):
        """
        Initialize with repositories.

        Args:
            ambiguous_term_repo: Repository for ambiguous terms
            user_preference_repo: Repository for user preferences
            entity_embedding_service: Optional service for ML recommendations (Phase 2)
        """
        self.ambiguous_term_repo = ambiguous_term_repo
        self.user_preference_repo = user_preference_repo
        self.entity_embedding_service = entity_embedding_service

    async def check_needs_clarification(
        self,
        request: ClarificationCheckRequest,
        user_id: str,
        use_ml_recommendation: bool = True,
    ) -> ClarificationCheckResponse:
        """
        Check if a query contains ambiguous terms that need clarification.

        This method:
        1. Finds ambiguous terms in the query
        2. Checks user preferences for auto-resolution
        3. Optionally adds ML-based entity recommendations (Phase 2)
        4. Returns terms needing clarification or auto-resolved query

        Args:
            request: Clarification check request with query
            user_id: User ID for preference lookup
            use_ml_recommendation: Whether to include ML recommendations (default True)

        Returns:
            ClarificationCheckResponse indicating if clarification is needed
        """
        query = request.query.strip()

        # 1. 쿼리에서 모호한 용어 찾기
        matching_terms = await self.ambiguous_term_repo.find_matching_terms(query)

        if not matching_terms:
            # 모호한 용어 없음 - 바로 검색 가능
            return ClarificationCheckResponse(
                needs_clarification=False,
                detected_terms=[],
                resolved_query=query,
                auto_resolved_count=0,
            )

        # 2. 발견된 용어들에 대한 사용자 선호도 조회
        term_names = [t['term_normalized'] for t in matching_terms]
        user_preferences = await self.user_preference_repo.get_user_preferences(
            user_id, term_names
        )

        # 3. 각 용어에 대해 처리
        detected_terms: List[DetectedAmbiguousTerm] = []
        terms_needing_clarification: List[DetectedAmbiguousTerm] = []
        auto_resolved_terms: List[Dict[str, str]] = []

        for term_data in matching_terms:
            normalized = term_data['term_normalized']
            user_pref = user_preferences.get(normalized)

            # 가능한 엔티티들을 모델로 변환
            possible_entities = [
                PossibleEntity(
                    id=e.get('id', ''),
                    name=e.get('name', ''),
                    description=e.get('description', ''),
                    keywords=e.get('keywords', [])
                )
                for e in term_data.get('possible_entities', [])
            ]

            # ML 추천 생성 (Phase 2)
            ml_recommendation = None
            if (
                use_ml_recommendation
                and self.entity_embedding_service is not None
                and possible_entities
            ):
                ml_recommendation = await self._get_ml_recommendation(
                    query, possible_entities, term_data
                )

            detected = DetectedAmbiguousTerm(
                term=term_data['term'],
                term_normalized=normalized,
                position_start=term_data.get('position_start', 0),
                position_end=term_data.get('position_end', 0),
                possible_entities=possible_entities,
                category=term_data.get('category'),
                user_preference=user_pref['selected_entity_id'] if user_pref else None,
                ml_recommendation=ml_recommendation,
            )

            detected_terms.append(detected)

            if user_pref and user_pref.get('is_permanent', False):
                # 영구 선호도가 있으면 자동 해결
                auto_resolved_terms.append({
                    'term': term_data['term'],
                    'entity_id': user_pref['selected_entity_id'],
                    'entity_name': user_pref['selected_entity_name'],
                })
                # 사용 횟수 증가
                await self.user_preference_repo.increment_usage(user_id, normalized)
            else:
                # 명확화 필요
                terms_needing_clarification.append(detected)

        # 4. 결과 생성
        if not terms_needing_clarification:
            # 모든 용어가 자동 해결됨
            resolved_query = self._apply_resolutions(query, auto_resolved_terms)
            return ClarificationCheckResponse(
                needs_clarification=False,
                detected_terms=detected_terms,
                resolved_query=resolved_query,
                auto_resolved_count=len(auto_resolved_terms),
                message=self._format_auto_resolve_message(auto_resolved_terms),
            )
        else:
            # 일부 용어는 명확화 필요
            return ClarificationCheckResponse(
                needs_clarification=True,
                detected_terms=terms_needing_clarification,
                resolved_query=None,
                auto_resolved_count=len(auto_resolved_terms),
            )

    async def _get_ml_recommendation(
        self,
        query: str,
        possible_entities: List[PossibleEntity],
        term_data: Dict[str, Any],
    ) -> Optional[MLRecommendation]:
        """
        Get ML-based entity recommendation for a term.

        Args:
            query: User query text
            possible_entities: List of possible entities
            term_data: Raw term data from repository (includes entity_embeddings)

        Returns:
            MLRecommendation or None if embeddings not available
        """
        try:
            # entity_embeddings 필드에서 임베딩 가져오기
            entity_embeddings = term_data.get('entity_embeddings')

            if not entity_embeddings:
                logger.debug(f"No embeddings for term '{term_data['term']}', skipping ML recommendation")
                return None

            # 임베딩 서비스로 추천 받기
            entity_id, entity_name, confidence = await self.entity_embedding_service.recommend_entity(
                query=query,
                possible_entities=possible_entities,
                entity_embeddings=entity_embeddings,
            )

            # 최소 신뢰도 임계값 (20% 미만이면 추천하지 않음)
            if confidence < 0.2:
                logger.debug(
                    f"ML recommendation confidence too low: {confidence:.2f} for term '{term_data['term']}'"
                )
                return None

            return MLRecommendation(
                entity_id=entity_id,
                entity_name=entity_name,
                confidence=round(confidence, 3),
            )

        except Exception as e:
            logger.warning(f"Failed to get ML recommendation: {e}")
            return None

    async def apply_user_selections(
        self,
        request: ClarificationApplyRequest,
        user_id: str
    ) -> ClarificationApplyResponse:
        """
        Apply user's clarification selections to resolve the query.

        This method:
        1. Validates selections
        2. Saves preferences if requested
        3. Returns resolved query

        Args:
            request: Apply request with query and selections
            user_id: User ID for saving preferences

        Returns:
            ClarificationApplyResponse with resolved query
        """
        query = request.query.strip()
        selections = request.selections

        applied_selections: List[Dict[str, str]] = []
        preferences_saved = 0

        # 1. 각 선택에 대해 처리
        for selection in selections:
            # 선택 적용
            applied_selections.append({
                'term': selection.term,
                'entity_id': selection.selected_entity_id,
                'entity_name': selection.selected_entity_name,
            })

            # 2. 선호도 저장 (remember=True인 경우)
            if selection.remember:
                await self.user_preference_repo.save_preference(
                    user_id=user_id,
                    term_normalized=selection.term.lower().strip(),
                    selected_entity_id=selection.selected_entity_id,
                    selected_entity_name=selection.selected_entity_name,
                    is_permanent=True,
                )
                preferences_saved += 1

        # 3. 쿼리에 해결된 용어 적용
        resolved_query = self._apply_resolutions(query, applied_selections)

        logger.info(
            f"Applied clarifications: user={user_id[:8]}..., "
            f"selections={len(applied_selections)}, saved={preferences_saved}"
        )

        return ClarificationApplyResponse(
            success=True,
            resolved_query=resolved_query,
            applied_selections=applied_selections,
            preferences_saved=preferences_saved,
            message=self._format_apply_message(applied_selections, preferences_saved),
        )

    def _apply_resolutions(
        self,
        query: str,
        resolutions: List[Dict[str, str]]
    ) -> str:
        """
        Apply term resolutions to the query.

        예: "MFS 에러" + [{"term": "MFS", "entity_name": "JEUS MFS"}]
        결과: "JEUS MFS 에러"

        Args:
            query: Original query
            resolutions: List of {term, entity_id, entity_name} dicts

        Returns:
            Resolved query with clarified terms
        """
        resolved = query

        for resolution in resolutions:
            term = resolution['term']
            entity_name = resolution['entity_name']

            # 대소문자 무시하고 용어 교체
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            resolved = pattern.sub(entity_name, resolved, count=1)

        return resolved

    def _format_auto_resolve_message(
        self,
        resolutions: List[Dict[str, str]]
    ) -> str:
        """Format message for auto-resolved terms."""
        if not resolutions:
            return ""

        parts = [f'"{r["term"]}" → {r["entity_name"]}' for r in resolutions]
        return "자동 해석: " + ", ".join(parts)

    def _format_apply_message(
        self,
        applied: List[Dict[str, str]],
        saved: int
    ) -> str:
        """Format message for applied selections."""
        parts = [f'"{a["term"]}" → {a["entity_name"]}' for a in applied]
        msg = "적용됨: " + ", ".join(parts)
        if saved > 0:
            msg += f" ({saved}개 선호도 저장됨)"
        return msg


# =============================================================================
# Service Factory
# =============================================================================

_query_clarification_service: Optional[QueryClarificationService] = None


def get_query_clarification_service() -> QueryClarificationService:
    """Get the query clarification service singleton."""
    global _query_clarification_service
    if _query_clarification_service is None:
        raise RuntimeError("QueryClarificationService not initialized. Call initialize_query_clarification_service first.")
    return _query_clarification_service


def initialize_query_clarification_service(
    ambiguous_term_repo: PostgresAmbiguousTermRepository,
    user_preference_repo: PostgresUserTermPreferenceRepository,
    entity_embedding_service: Optional[Any] = None,
) -> QueryClarificationService:
    """
    Initialize the query clarification service singleton.

    Args:
        ambiguous_term_repo: Repository for ambiguous terms
        user_preference_repo: Repository for user preferences
        entity_embedding_service: Optional service for ML recommendations (Phase 2)

    Returns:
        Initialized QueryClarificationService
    """
    global _query_clarification_service
    _query_clarification_service = QueryClarificationService(
        ambiguous_term_repo=ambiguous_term_repo,
        user_preference_repo=user_preference_repo,
        entity_embedding_service=entity_embedding_service,
    )

    if entity_embedding_service:
        logger.info("QueryClarificationService initialized with ML recommendations")
    else:
        logger.info("QueryClarificationService initialized (ML recommendations disabled)")

    return _query_clarification_service


def set_query_clarification_service(service: QueryClarificationService) -> None:
    """Set the query clarification service singleton."""
    global _query_clarification_service
    _query_clarification_service = service
