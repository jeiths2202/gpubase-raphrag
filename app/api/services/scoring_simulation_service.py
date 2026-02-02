"""
Scoring Simulation Service

Provides simulation capabilities for testing scoring configuration changes:
- Run search with specific config and return detailed scoring breakdown
- Compare two configurations side-by-side
- Batch test against expected results
"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from ..models.scoring_config import (
    ScoringConfig,
    SimulationResult,
    SimulationStep,
    RankedDocument,
    ComparisonResult,
    TestCase,
    TestCaseResult,
    BatchTestResult,
)
from .scoring_config_service import get_scoring_config_service

logger = logging.getLogger(__name__)


@dataclass
class SimulationContext:
    """Context for a simulation run"""
    query: str
    config: ScoringConfig
    debug_info: Dict[str, Any] = field(default_factory=dict)


class ScoringSimulationService:
    """
    Service for simulating search scoring with different configurations.

    Allows testing configuration changes before applying them to production.
    """

    def __init__(self, search_service=None, vector_store=None):
        """
        Initialize simulation service.

        Args:
            search_service: Optional search service for actual queries
            vector_store: Optional vector store for embeddings
        """
        self._search_service = search_service
        self._vector_store = vector_store

    async def simulate(
        self,
        query: str,
        config: Optional[ScoringConfig] = None
    ) -> SimulationResult:
        """
        Run a search simulation with the specified configuration.

        Args:
            query: Search query to simulate
            config: Configuration to use (uses active if not provided)

        Returns:
            SimulationResult with detailed scoring breakdown
        """
        start_time = time.time()
        steps: List[SimulationStep] = []

        # Get config
        if config is None:
            service = get_scoring_config_service()
            config = await service.get_active_config()

        context = SimulationContext(query=query, config=config)

        # Step 1: Query Analysis
        query_analysis = self._analyze_query(query, config)
        steps.append(SimulationStep(
            name="Query Analysis",
            description="Analyze query for keywords, patterns, and intent",
            input_data={"query": query},
            output_data=query_analysis,
            score_impact=0.0,
            details=query_analysis
        ))

        # Step 2: Vector Search Simulation
        vector_results = await self._simulate_vector_search(query, config)
        steps.append(SimulationStep(
            name="Vector Search",
            description="Semantic similarity search using embeddings",
            input_data={"query": query, "top_k": config.search.default_top_k},
            output_data={"results_count": len(vector_results)},
            score_impact=config.rrf.neo4j_weight,
            details={"top_results": vector_results[:5]}
        ))

        # Step 3: Keyword Search Simulation
        keyword_results = await self._simulate_keyword_search(query, config)
        steps.append(SimulationStep(
            name="Keyword Search (BM25)",
            description=f"BM25 search with k1={config.bm25.k1}, b={config.bm25.b}",
            input_data={"query": query, "k1": config.bm25.k1, "b": config.bm25.b},
            output_data={"results_count": len(keyword_results)},
            score_impact=config.rrf.postgres_weight,
            details={"top_results": keyword_results[:5]}
        ))

        # Step 4: RRF Fusion
        fused_results = self._simulate_rrf_fusion(
            vector_results, keyword_results, config
        )
        steps.append(SimulationStep(
            name="RRF Fusion",
            description=f"Reciprocal Rank Fusion with k={config.rrf.k}",
            input_data={
                "k": config.rrf.k,
                "neo4j_weight": config.rrf.neo4j_weight,
                "postgres_weight": config.rrf.postgres_weight
            },
            output_data={"fused_count": len(fused_results)},
            score_impact=1.0,
            details={"fusion_formula": "1/(k + rank)"}
        ))

        # Step 5: Boost Application
        boosted_results = self._apply_boosts(fused_results, query, config)
        boost_applied = []
        if config.boost.title_match_enabled:
            boost_applied.append(f"title_match: {config.boost.title_match_boost}x")
        if config.boost.error_code_enabled:
            boost_applied.append(f"error_code: {config.boost.error_code_boost}x")

        steps.append(SimulationStep(
            name="Score Boosting",
            description="Apply boost multipliers for matches",
            input_data={"boosts_enabled": boost_applied},
            output_data={"boosted_count": len(boosted_results)},
            score_impact=max(config.boost.title_match_boost, config.boost.error_code_boost) - 1.0,
            details={"boost_config": {
                "title_match": config.boost.title_match_boost,
                "error_code": config.boost.error_code_boost,
                "exact_phrase": config.boost.exact_phrase_boost
            }}
        ))

        # Step 6: Final Ranking
        final_ranking = self._create_final_ranking(boosted_results, config)
        steps.append(SimulationStep(
            name="Final Ranking",
            description="Sort by final score and apply confidence thresholds",
            input_data={
                "high_threshold": config.confidence.high_threshold,
                "medium_threshold": config.confidence.medium_threshold
            },
            output_data={"final_count": len(final_ranking)},
            score_impact=0.0,
            details={"confidence_distribution": self._get_confidence_distribution(final_ranking, config)}
        ))

        execution_time = (time.time() - start_time) * 1000

        return SimulationResult(
            query=query,
            config=config,
            steps=steps,
            final_ranking=final_ranking,
            execution_time_ms=execution_time,
            debug_info={
                "total_steps": len(steps),
                "vector_results": len(vector_results),
                "keyword_results": len(keyword_results),
                "final_results": len(final_ranking)
            }
        )

    async def compare(
        self,
        query: str,
        config_a: Optional[ScoringConfig] = None,
        config_b: ScoringConfig = None
    ) -> ComparisonResult:
        """
        Compare search results between two configurations.

        Args:
            query: Search query for comparison
            config_a: First config (uses active if not provided)
            config_b: Second config to compare against

        Returns:
            ComparisonResult showing differences
        """
        # Get config A
        if config_a is None:
            service = get_scoring_config_service()
            config_a = await service.get_active_config()

        # Run both simulations
        result_a = await self.simulate(query, config_a)
        result_b = await self.simulate(query, config_b)

        # Analyze differences
        rank_changes = self._calculate_rank_changes(
            result_a.final_ranking,
            result_b.final_ranking
        )

        # Find new and removed entries
        ids_a = {doc.document_id for doc in result_a.final_ranking}
        ids_b = {doc.document_id for doc in result_b.final_ranking}

        new_entries = [
            doc for doc in result_b.final_ranking
            if doc.document_id not in ids_a
        ]
        removed_entries = [
            doc for doc in result_a.final_ranking
            if doc.document_id not in ids_b
        ]

        # Calculate score deltas
        score_deltas = {}
        scores_a = {doc.document_id: doc.final_score for doc in result_a.final_ranking}
        for doc in result_b.final_ranking:
            if doc.document_id in scores_a:
                delta = doc.final_score - scores_a[doc.document_id]
                if abs(delta) > 0.01:  # Only significant changes
                    score_deltas[doc.document_id] = delta

        return ComparisonResult(
            query=query,
            config_a=config_a,
            config_b=config_b,
            result_a=result_a,
            result_b=result_b,
            rank_changes=rank_changes,
            new_entries=new_entries,
            removed_entries=removed_entries,
            score_deltas=score_deltas
        )

    async def batch_test(
        self,
        test_cases: List[TestCase],
        config: Optional[ScoringConfig] = None
    ) -> BatchTestResult:
        """
        Run batch tests against a configuration.

        Args:
            test_cases: List of test cases with expected results
            config: Configuration to test (uses active if not provided)

        Returns:
            BatchTestResult with pass/fail results
        """
        if config is None:
            service = get_scoring_config_service()
            config = await service.get_active_config()

        results: List[TestCaseResult] = []
        passed = 0
        failed = 0

        for test_case in test_cases:
            result = await self._run_test_case(test_case, config)
            results.append(result)

            if result.passed:
                passed += 1
            else:
                failed += 1

        # Identify improved and degraded cases (compared to baseline)
        improved_cases = [r for r in results if r.passed and r.details.get("was_failing", False)]
        degraded_cases = [r for r in results if not r.passed and r.details.get("was_passing", False)]

        return BatchTestResult(
            config=config,
            total_cases=len(test_cases),
            passed=passed,
            failed=failed,
            pass_rate=passed / len(test_cases) if test_cases else 0.0,
            results=results,
            improved_cases=improved_cases,
            degraded_cases=degraded_cases
        )

    # Private helper methods

    def _analyze_query(self, query: str, config: ScoringConfig) -> Dict[str, Any]:
        """Analyze query for patterns and intent."""
        import re

        analysis = {
            "original_query": query,
            "length": len(query),
            "word_count": len(query.split()),
            "patterns_detected": [],
            "language_hints": []
        }

        # Detect error code pattern
        if re.search(r'-?\d{4,5}', query):
            analysis["patterns_detected"].append("error_code")

        # Detect quoted phrase
        if '"' in query or "'" in query:
            analysis["patterns_detected"].append("exact_phrase")

        # Detect web search prefix
        if query.startswith("@"):
            analysis["patterns_detected"].append("web_priority")

        # Language detection hints
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', query):
            analysis["language_hints"].append("japanese")
        if re.search(r'[\uac00-\ud7af]', query):
            analysis["language_hints"].append("korean")
        if re.search(r'[\u4e00-\u9fff]', query):
            analysis["language_hints"].append("chinese")

        return analysis

    async def _simulate_vector_search(
        self,
        query: str,
        config: ScoringConfig
    ) -> List[Dict[str, Any]]:
        """Simulate vector search results."""
        # In a real implementation, this would call the actual vector store
        # For simulation, return mock results
        return [
            {"document_id": f"doc_{i}", "title": f"Document {i}",
             "score": 0.9 - (i * 0.1), "source": "neo4j"}
            for i in range(config.search.default_top_k)
        ]

    async def _simulate_keyword_search(
        self,
        query: str,
        config: ScoringConfig
    ) -> List[Dict[str, Any]]:
        """Simulate BM25 keyword search results."""
        # Mock results for simulation
        return [
            {"document_id": f"doc_{i+2}", "title": f"Document {i+2}",
             "score": 0.85 - (i * 0.1), "source": "postgres"}
            for i in range(config.search.default_top_k)
        ]

    def _simulate_rrf_fusion(
        self,
        vector_results: List[Dict],
        keyword_results: List[Dict],
        config: ScoringConfig
    ) -> List[Dict[str, Any]]:
        """Simulate RRF fusion of results."""
        k = config.rrf.k
        scores: Dict[str, float] = {}
        docs: Dict[str, Dict] = {}

        # Score from vector results
        for rank, doc in enumerate(vector_results, 1):
            doc_id = doc["document_id"]
            rrf_score = config.rrf.neo4j_weight / (k + rank)
            scores[doc_id] = scores.get(doc_id, 0) + rrf_score
            docs[doc_id] = doc

        # Score from keyword results
        for rank, doc in enumerate(keyword_results, 1):
            doc_id = doc["document_id"]
            rrf_score = config.rrf.postgres_weight / (k + rank)
            scores[doc_id] = scores.get(doc_id, 0) + rrf_score
            if doc_id not in docs:
                docs[doc_id] = doc

        # Sort by fused score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        return [
            {**docs[doc_id], "rrf_score": scores[doc_id]}
            for doc_id in sorted_ids
        ]

    def _apply_boosts(
        self,
        results: List[Dict],
        query: str,
        config: ScoringConfig
    ) -> List[Dict[str, Any]]:
        """Apply boost multipliers to results."""
        boosted = []
        query_lower = query.lower()

        for doc in results:
            boost_multiplier = 1.0
            boosts_applied = []

            title = doc.get("title", "").lower()

            # Title match boost
            if config.boost.title_match_enabled:
                query_words = query_lower.split()
                if any(word in title for word in query_words):
                    boost_multiplier *= config.boost.title_match_boost
                    boosts_applied.append("title_match")

            # Error code boost
            if config.boost.error_code_enabled:
                import re
                if re.search(r'-?\d{4,5}', query):
                    if "error" in title or "에러" in title or "エラー" in title:
                        boost_multiplier *= config.boost.error_code_boost
                        boosts_applied.append("error_code")

            final_score = doc.get("rrf_score", 0.5) * boost_multiplier

            boosted.append({
                **doc,
                "boost_multiplier": boost_multiplier,
                "boosts_applied": boosts_applied,
                "final_score": final_score
            })

        # Re-sort by boosted score
        boosted.sort(key=lambda x: x["final_score"], reverse=True)
        return boosted

    def _create_final_ranking(
        self,
        results: List[Dict],
        config: ScoringConfig
    ) -> List[RankedDocument]:
        """Create final ranking with confidence levels."""
        ranking = []

        for rank, doc in enumerate(results, 1):
            score = doc.get("final_score", 0.0)

            # Determine confidence level
            if score >= config.confidence.high_threshold:
                confidence = "high"
            elif score >= config.confidence.medium_threshold:
                confidence = "medium"
            else:
                confidence = "low"

            ranking.append(RankedDocument(
                rank=rank,
                document_id=doc.get("document_id", ""),
                title=doc.get("title", ""),
                final_score=score,
                confidence_level=confidence,
                score_breakdown={
                    "rrf_score": doc.get("rrf_score", 0.0),
                    "boost_multiplier": doc.get("boost_multiplier", 1.0),
                    "boosts_applied": doc.get("boosts_applied", [])
                }
            ))

        return ranking

    def _get_confidence_distribution(
        self,
        ranking: List[RankedDocument],
        config: ScoringConfig
    ) -> Dict[str, int]:
        """Get distribution of confidence levels."""
        distribution = {"high": 0, "medium": 0, "low": 0}

        for doc in ranking:
            level = doc.confidence_level
            if level in distribution:
                distribution[level] += 1

        return distribution

    def _calculate_rank_changes(
        self,
        ranking_a: List[RankedDocument],
        ranking_b: List[RankedDocument]
    ) -> List[Dict[str, Any]]:
        """Calculate rank changes between two rankings."""
        changes = []

        ranks_a = {doc.document_id: doc.rank for doc in ranking_a}

        for doc in ranking_b:
            if doc.document_id in ranks_a:
                old_rank = ranks_a[doc.document_id]
                new_rank = doc.rank
                change = old_rank - new_rank  # Positive = moved up

                if change != 0:
                    changes.append({
                        "document_id": doc.document_id,
                        "title": doc.title,
                        "old_rank": old_rank,
                        "new_rank": new_rank,
                        "change": change,
                        "direction": "up" if change > 0 else "down"
                    })

        # Sort by absolute change
        changes.sort(key=lambda x: abs(x["change"]), reverse=True)
        return changes

    async def _run_test_case(
        self,
        test_case: TestCase,
        config: ScoringConfig
    ) -> TestCaseResult:
        """Run a single test case."""
        result = await self.simulate(test_case.query, config)

        # Check if expected documents are in top N
        top_ids = [doc.document_id for doc in result.final_ranking[:test_case.expected_top_n]]

        found_expected = []
        missing_expected = []

        for expected_id in test_case.expected_documents:
            if expected_id in top_ids:
                found_expected.append(expected_id)
            else:
                missing_expected.append(expected_id)

        passed = len(missing_expected) == 0

        return TestCaseResult(
            test_case=test_case,
            passed=passed,
            actual_ranking=result.final_ranking[:test_case.expected_top_n],
            found_expected=found_expected,
            missing_expected=missing_expected,
            details={
                "query": test_case.query,
                "expected_top_n": test_case.expected_top_n,
                "expected_documents": test_case.expected_documents
            }
        )


# Singleton instance
_simulation_service: Optional[ScoringSimulationService] = None


def get_simulation_service(
    search_service=None,
    vector_store=None
) -> ScoringSimulationService:
    """Get or create the simulation service singleton."""
    global _simulation_service

    if _simulation_service is None:
        _simulation_service = ScoringSimulationService(search_service, vector_store)

    return _simulation_service
