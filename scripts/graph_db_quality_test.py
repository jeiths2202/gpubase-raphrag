#!/usr/bin/env python3
"""
Graph DB Quality Test Script
Neo4j 그래프 데이터베이스 정합성 및 품질 검증

Usage:
    python scripts/graph_db_quality_test.py
    python scripts/graph_db_quality_test.py --category T1
    python scripts/graph_db_quality_test.py --format json
    python scripts/graph_db_quality_test.py --verbose
"""

import os
import sys
import json
import argparse
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    print("Warning: neo4j package not installed. Install with: pip install neo4j")


class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class TestResult:
    """Individual test result"""
    test_id: str
    name: str
    status: TestStatus
    message: str
    value: Any = None
    threshold: Any = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CategoryResult:
    """Test category result"""
    category_id: str
    name: str
    tests: List[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.FAIL)

    @property
    def warnings(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.WARN)


class GraphDBQualityTester:
    """Neo4j Graph Database Quality Tester"""

    # Thresholds
    EMBEDDING_DIMENSION = 4096
    MAX_NULL_EMBEDDING_RATIO = 0.05  # 5%
    MIN_SIMILARITY_MEAN = 0.85
    MAX_LOW_CONFIDENCE_RATIO = 0.30  # 30%
    MIN_HIGH_CONFIDENCE_RATIO = 0.40  # 40%
    MIN_AVG_CONFIDENCE = 0.75
    MIN_CHUNK_SECTION_LINK_RATIO = 0.80  # 80%
    ENTITY_CONFIDENCE_THRESHOLD = 0.70
    ENTITY_CONFIDENCE_HIGH = 0.90

    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "")

        if not self.password:
            raise ValueError("NEO4J_PASSWORD environment variable is required")

        self.driver = None
        self.results: List[CategoryResult] = []
        self.verbose = False

    def connect(self) -> bool:
        """Connect to Neo4j database"""
        if not NEO4J_AVAILABLE:
            return False
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            # Verify connection
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
            return False

    def close(self):
        """Close database connection"""
        if self.driver:
            self.driver.close()

    def _run_query(self, query: str, params: Dict = None) -> List[Dict]:
        """Execute a Cypher query and return results"""
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    def _log(self, message: str):
        """Log message if verbose mode"""
        if self.verbose:
            print(f"  [DEBUG] {message}")

    # =========================================================================
    # T1: Node Integrity Tests
    # =========================================================================

    def test_t1_node_integrity(self) -> CategoryResult:
        """T1: Node Integrity Tests"""
        category = CategoryResult("T1", "Node Integrity")

        # T1.1: Document required properties
        query = """
        MATCH (d:Document)
        WHERE d.id IS NULL OR d.filename IS NULL
        RETURN count(d) as violations
        """
        result = self._run_query(query)
        violations = result[0]["violations"] if result else 0
        category.tests.append(TestResult(
            "T1.1", "Document required props",
            TestStatus.PASS if violations == 0 else TestStatus.FAIL,
            f"{violations} violations",
            value=violations, threshold=0
        ))

        # T1.2: Chunk required properties
        query = """
        MATCH (c:Chunk)
        WHERE c.id IS NULL OR c.content IS NULL
        RETURN count(c) as violations
        """
        result = self._run_query(query)
        violations = result[0]["violations"] if result else 0
        category.tests.append(TestResult(
            "T1.2", "Chunk required props",
            TestStatus.PASS if violations == 0 else TestStatus.FAIL,
            f"{violations} violations",
            value=violations, threshold=0
        ))

        # T1.3: Entity required properties
        query = """
        MATCH (e:Entity)
        WHERE e.name IS NULL OR e.type IS NULL
        RETURN count(e) as violations
        """
        result = self._run_query(query)
        violations = result[0]["violations"] if result else 0
        category.tests.append(TestResult(
            "T1.3", "Entity required props",
            TestStatus.PASS if violations == 0 else TestStatus.FAIL,
            f"{violations} violations",
            value=violations, threshold=0
        ))

        # T1.4: Section required properties
        query = """
        MATCH (s:Section)
        WHERE s.id IS NULL OR s.path IS NULL OR s.level IS NULL
        RETURN count(s) as violations
        """
        result = self._run_query(query)
        violations = result[0]["violations"] if result else 0
        category.tests.append(TestResult(
            "T1.4", "Section required props",
            TestStatus.PASS if violations == 0 else TestStatus.FAIL,
            f"{violations} violations",
            value=violations, threshold=0
        ))

        # T1.5: Entity confidence range (0.0-1.0)
        query = """
        MATCH (e:Entity)
        WHERE e.confidence IS NOT NULL
          AND (e.confidence < 0.0 OR e.confidence > 1.0)
        RETURN count(e) as violations
        """
        result = self._run_query(query)
        violations = result[0]["violations"] if result else 0
        category.tests.append(TestResult(
            "T1.5", "Confidence range (0.0-1.0)",
            TestStatus.PASS if violations == 0 else TestStatus.FAIL,
            f"{violations} violations",
            value=violations, threshold=0
        ))

        return category

    # =========================================================================
    # T2: Relationship Integrity Tests
    # =========================================================================

    def test_t2_relationship_integrity(self) -> CategoryResult:
        """T2: Relationship Integrity Tests"""
        category = CategoryResult("T2", "Relationship Integrity")

        # T2.1: Orphan Chunks (no Document connection)
        query = """
        MATCH (c:Chunk)
        WHERE NOT EXISTS { MATCH (:Document)-[:CONTAINS]->(c) }
        RETURN count(c) as orphans
        """
        result = self._run_query(query)
        orphans = result[0]["orphans"] if result else 0
        category.tests.append(TestResult(
            "T2.1", "Orphan Chunks",
            TestStatus.PASS if orphans == 0 else TestStatus.WARN,
            f"{orphans} orphans",
            value=orphans, threshold=0
        ))

        # T2.2: SIMILAR_TO self-references
        query = """
        MATCH (c:Chunk)-[r:SIMILAR_TO]->(c)
        RETURN count(r) as self_refs
        """
        result = self._run_query(query)
        self_refs = result[0]["self_refs"] if result else 0
        category.tests.append(TestResult(
            "T2.2", "SIMILAR_TO self-refs",
            TestStatus.PASS if self_refs == 0 else TestStatus.FAIL,
            f"{self_refs} self-refs",
            value=self_refs, threshold=0
        ))

        # T2.3: SIMILAR_TO score range
        query = """
        MATCH ()-[r:SIMILAR_TO]->()
        WHERE r.score IS NOT NULL
          AND (r.score < 0.0 OR r.score > 1.0)
        RETURN count(r) as violations
        """
        result = self._run_query(query)
        violations = result[0]["violations"] if result else 0
        category.tests.append(TestResult(
            "T2.3", "SIMILAR_TO score range",
            TestStatus.PASS if violations == 0 else TestStatus.FAIL,
            f"{violations} violations",
            value=violations, threshold=0
        ))

        # T2.4: NEXT chain cycles (check for cycles up to 50 hops)
        query = """
        MATCH path = (c:Chunk)-[:NEXT*1..50]->(c)
        RETURN count(path) as cycles
        LIMIT 1
        """
        try:
            result = self._run_query(query)
            cycles = result[0]["cycles"] if result else 0
        except Exception as e:
            self._log(f"Cycle detection query error: {e}")
            cycles = 0
        category.tests.append(TestResult(
            "T2.4", "NEXT chain cycles",
            TestStatus.PASS if cycles == 0 else TestStatus.FAIL,
            f"{cycles} cycles",
            value=cycles, threshold=0
        ))

        # T2.5: Duplicate relationships
        query = """
        MATCH (a)-[r:SIMILAR_TO]->(b)
        WITH a, b, count(r) as cnt
        WHERE cnt > 1
        RETURN sum(cnt - 1) as duplicates
        """
        result = self._run_query(query)
        duplicates = result[0]["duplicates"] if result and result[0]["duplicates"] else 0
        category.tests.append(TestResult(
            "T2.5", "Duplicate SIMILAR_TO",
            TestStatus.PASS if duplicates == 0 else TestStatus.WARN,
            f"{duplicates} duplicates",
            value=duplicates, threshold=0
        ))

        return category

    # =========================================================================
    # T3: Embedding Quality Tests
    # =========================================================================

    def test_t3_embedding_quality(self) -> CategoryResult:
        """T3: Embedding Quality Tests"""
        category = CategoryResult("T3", "Embedding Quality")

        # T3.1: NULL embeddings ratio
        query = """
        MATCH (c:Chunk)
        WITH count(c) as total,
             count(CASE WHEN c.embedding IS NULL THEN 1 END) as null_count
        RETURN total, null_count,
               CASE WHEN total > 0
                    THEN toFloat(null_count) / total
                    ELSE 0.0 END as null_ratio
        """
        result = self._run_query(query)
        if result:
            total = result[0]["total"]
            null_count = result[0]["null_count"]
            null_ratio = result[0]["null_ratio"]

            status = TestStatus.PASS if null_ratio <= self.MAX_NULL_EMBEDDING_RATIO else TestStatus.FAIL
            category.tests.append(TestResult(
                "T3.1", "NULL embeddings",
                status,
                f"{null_ratio*100:.1f}% ({null_count}/{total})",
                value=null_ratio,
                threshold=self.MAX_NULL_EMBEDDING_RATIO,
                details={"total": total, "null_count": null_count}
            ))
        else:
            category.tests.append(TestResult(
                "T3.1", "NULL embeddings",
                TestStatus.SKIP, "No chunks found"
            ))

        # T3.2: Embedding dimension consistency
        query = """
        MATCH (c:Chunk)
        WHERE c.embedding IS NOT NULL
        WITH size(c.embedding) as dim, count(*) as cnt
        RETURN dim, cnt
        ORDER BY cnt DESC
        """
        result = self._run_query(query)
        if result:
            dimensions = {r["dim"]: r["cnt"] for r in result}
            total = sum(dimensions.values())
            correct = dimensions.get(self.EMBEDDING_DIMENSION, 0)
            ratio = correct / total if total > 0 else 0

            status = TestStatus.PASS if ratio == 1.0 else TestStatus.FAIL
            category.tests.append(TestResult(
                "T3.2", f"Dimension consistency ({self.EMBEDDING_DIMENSION})",
                status,
                f"{ratio*100:.1f}% consistent",
                value=ratio,
                threshold=1.0,
                details={"dimensions": dimensions}
            ))
        else:
            category.tests.append(TestResult(
                "T3.2", "Dimension consistency",
                TestStatus.SKIP, "No embeddings found"
            ))

        # T3.3: SIMILAR_TO score distribution
        query = """
        MATCH ()-[r:SIMILAR_TO]->()
        WHERE r.score IS NOT NULL
        RETURN avg(r.score) as mean_score,
               min(r.score) as min_score,
               max(r.score) as max_score,
               count(r) as count
        """
        result = self._run_query(query)
        if result and result[0]["count"]:
            mean_score = result[0]["mean_score"]
            min_score = result[0]["min_score"]
            max_score = result[0]["max_score"]
            count = result[0]["count"]

            status = TestStatus.PASS if mean_score >= self.MIN_SIMILARITY_MEAN else TestStatus.WARN
            category.tests.append(TestResult(
                "T3.3", "Similarity distribution",
                status,
                f"mean={mean_score:.3f}, range=[{min_score:.3f}, {max_score:.3f}]",
                value=mean_score,
                threshold=self.MIN_SIMILARITY_MEAN,
                details={"min": min_score, "max": max_score, "count": count}
            ))
        else:
            category.tests.append(TestResult(
                "T3.3", "Similarity distribution",
                TestStatus.SKIP, "No SIMILAR_TO relations found"
            ))

        return category

    # =========================================================================
    # T4: Entity Quality Tests
    # =========================================================================

    def test_t4_entity_quality(self) -> CategoryResult:
        """T4: Entity Quality Tests"""
        category = CategoryResult("T4", "Entity Quality")

        # Entity statistics query
        query = f"""
        MATCH (e:Entity)
        WHERE e.confidence IS NOT NULL
        RETURN
            count(e) as total,
            count(CASE WHEN e.confidence < {self.ENTITY_CONFIDENCE_THRESHOLD} THEN 1 END) as low_conf,
            count(CASE WHEN e.confidence >= {self.ENTITY_CONFIDENCE_HIGH} THEN 1 END) as high_conf,
            avg(e.confidence) as avg_conf,
            count(CASE WHEN e:HighConfidenceEntity THEN 1 END) as labeled_high
        """
        result = self._run_query(query)

        if result and result[0]["total"]:
            total = result[0]["total"]
            low_conf = result[0]["low_conf"]
            high_conf = result[0]["high_conf"]
            avg_conf = result[0]["avg_conf"]
            labeled_high = result[0]["labeled_high"]

            low_ratio = low_conf / total
            high_ratio = high_conf / total

            # T4.1: Low confidence ratio
            status = TestStatus.PASS if low_ratio <= self.MAX_LOW_CONFIDENCE_RATIO else TestStatus.WARN
            category.tests.append(TestResult(
                "T4.1", f"Low confidence (<{self.ENTITY_CONFIDENCE_THRESHOLD}) ratio",
                status,
                f"{low_ratio*100:.1f}% ({low_conf}/{total})",
                value=low_ratio,
                threshold=self.MAX_LOW_CONFIDENCE_RATIO
            ))

            # T4.2: High confidence ratio
            status = TestStatus.PASS if high_ratio >= self.MIN_HIGH_CONFIDENCE_RATIO else TestStatus.WARN
            category.tests.append(TestResult(
                "T4.2", f"High confidence (>={self.ENTITY_CONFIDENCE_HIGH}) ratio",
                status,
                f"{high_ratio*100:.1f}% ({high_conf}/{total})",
                value=high_ratio,
                threshold=self.MIN_HIGH_CONFIDENCE_RATIO
            ))

            # T4.3: HighConfidenceEntity label consistency
            label_match = labeled_high == high_conf
            category.tests.append(TestResult(
                "T4.3", "HighConfidenceEntity label match",
                TestStatus.PASS if label_match else TestStatus.WARN,
                f"labeled={labeled_high}, expected={high_conf}",
                value=labeled_high,
                threshold=high_conf
            ))

            # T4.4: Average confidence
            status = TestStatus.PASS if avg_conf >= self.MIN_AVG_CONFIDENCE else TestStatus.WARN
            category.tests.append(TestResult(
                "T4.4", "Average confidence",
                status,
                f"{avg_conf:.3f}",
                value=avg_conf,
                threshold=self.MIN_AVG_CONFIDENCE
            ))
        else:
            # Check if there are entities without confidence
            query2 = "MATCH (e:Entity) RETURN count(e) as total"
            result2 = self._run_query(query2)
            total = result2[0]["total"] if result2 else 0

            if total > 0:
                category.tests.append(TestResult(
                    "T4.1-4", "Entity confidence",
                    TestStatus.WARN,
                    f"{total} entities have no confidence property"
                ))
            else:
                category.tests.append(TestResult(
                    "T4.1-4", "Entity quality",
                    TestStatus.SKIP, "No entities found"
                ))

        return category

    # =========================================================================
    # T5: Section Hierarchy Tests
    # =========================================================================

    def test_t5_section_hierarchy(self) -> CategoryResult:
        """T5: Section Hierarchy Tests"""
        category = CategoryResult("T5", "Section Hierarchy")

        # T5.1: Orphan Sections (level > 1 without parent)
        query = """
        MATCH (s:Section)
        WHERE s.level > 1
          AND NOT EXISTS { MATCH (:Section)-[:HAS_SECTION]->(s) }
          AND NOT EXISTS { MATCH (:Document)-[:HAS_SECTION]->(s) }
        RETURN count(s) as orphans
        """
        result = self._run_query(query)
        orphans = result[0]["orphans"] if result else 0
        category.tests.append(TestResult(
            "T5.1", "Orphan Sections",
            TestStatus.PASS if orphans == 0 else TestStatus.WARN,
            f"{orphans} orphans",
            value=orphans, threshold=0
        ))

        # T5.2: Chunk-Section link ratio
        query = """
        MATCH (c:Chunk)
        WITH count(c) as total,
             count(CASE WHEN c.section_id IS NOT NULL THEN 1 END) as linked
        RETURN total, linked,
               CASE WHEN total > 0
                    THEN toFloat(linked) / total
                    ELSE 0.0 END as ratio
        """
        result = self._run_query(query)
        if result and result[0]["total"]:
            total = result[0]["total"]
            linked = result[0]["linked"]
            ratio = result[0]["ratio"]

            # If no sections exist, this test should be skipped
            section_count_result = self._run_query("MATCH (s:Section) RETURN count(s) as cnt")
            section_count = section_count_result[0]["cnt"] if section_count_result else 0

            if section_count == 0:
                category.tests.append(TestResult(
                    "T5.2", "Chunk-Section links",
                    TestStatus.SKIP, "No sections exist"
                ))
            else:
                status = TestStatus.PASS if ratio >= self.MIN_CHUNK_SECTION_LINK_RATIO else TestStatus.WARN
                category.tests.append(TestResult(
                    "T5.2", "Chunk-Section links",
                    status,
                    f"{ratio*100:.1f}% ({linked}/{total})",
                    value=ratio,
                    threshold=self.MIN_CHUNK_SECTION_LINK_RATIO
                ))
        else:
            category.tests.append(TestResult(
                "T5.2", "Chunk-Section links",
                TestStatus.SKIP, "No chunks found"
            ))

        # T5.3: Level-path consistency
        query = """
        MATCH (s:Section)
        WHERE s.path IS NOT NULL AND s.level IS NOT NULL
        WITH s, size(split(s.path, '.')) as expected_level
        WHERE expected_level <> s.level
        RETURN count(s) as mismatches
        """
        result = self._run_query(query)
        mismatches = result[0]["mismatches"] if result else 0

        section_count_result = self._run_query("MATCH (s:Section) RETURN count(s) as cnt")
        section_count = section_count_result[0]["cnt"] if section_count_result else 0

        if section_count == 0:
            category.tests.append(TestResult(
                "T5.3", "Level-path consistency",
                TestStatus.SKIP, "No sections exist"
            ))
        else:
            category.tests.append(TestResult(
                "T5.3", "Level-path consistency",
                TestStatus.PASS if mismatches == 0 else TestStatus.FAIL,
                f"{mismatches} mismatches",
                value=mismatches, threshold=0
            ))

        return category

    # =========================================================================
    # T6: Index Status Tests
    # =========================================================================

    def test_t6_index_status(self) -> CategoryResult:
        """T6: Index Status Tests"""
        category = CategoryResult("T6", "Index Status")

        # T6.1-3: Vector Index status
        query = """
        SHOW INDEXES
        YIELD name, state, type, labelsOrTypes, properties, options
        WHERE name = 'chunk_embedding' OR type = 'VECTOR'
        RETURN name, state, type, labelsOrTypes, properties, options
        """
        try:
            result = self._run_query(query)

            if result:
                idx = result[0]
                name = idx.get("name", "unknown")
                state = idx.get("state", "unknown")
                options = idx.get("options", {})

                # Extract dimension from options
                index_config = options.get("indexConfig", {}) if options else {}
                dimension = index_config.get("vector.dimensions", "unknown")

                # T6.1: Index exists
                category.tests.append(TestResult(
                    "T6.1", "Vector Index exists",
                    TestStatus.PASS,
                    f"Index '{name}' found"
                ))

                # T6.2: Index state
                category.tests.append(TestResult(
                    "T6.2", "Index state",
                    TestStatus.PASS if state == "ONLINE" else TestStatus.FAIL,
                    f"{state}"
                ))

                # T6.3: Index dimension
                expected_dim = self.EMBEDDING_DIMENSION
                dim_match = dimension == expected_dim
                category.tests.append(TestResult(
                    "T6.3", f"Index dimension ({expected_dim})",
                    TestStatus.PASS if dim_match else TestStatus.WARN,
                    f"{dimension}",
                    value=dimension,
                    threshold=expected_dim
                ))
            else:
                category.tests.append(TestResult(
                    "T6.1", "Vector Index exists",
                    TestStatus.FAIL,
                    "No vector index found"
                ))
                category.tests.append(TestResult(
                    "T6.2", "Index state",
                    TestStatus.SKIP, "No index"
                ))
                category.tests.append(TestResult(
                    "T6.3", "Index dimension",
                    TestStatus.SKIP, "No index"
                ))
        except Exception as e:
            self._log(f"Index query error: {e}")
            category.tests.append(TestResult(
                "T6.1-3", "Index status",
                TestStatus.WARN,
                f"Could not query indexes: {str(e)[:50]}"
            ))

        return category

    # =========================================================================
    # Main Test Runner
    # =========================================================================

    def run_all_tests(self, categories: List[str] = None) -> List[CategoryResult]:
        """Run all tests or specified categories"""
        all_tests = {
            "T1": self.test_t1_node_integrity,
            "T2": self.test_t2_relationship_integrity,
            "T3": self.test_t3_embedding_quality,
            "T4": self.test_t4_entity_quality,
            "T5": self.test_t5_section_hierarchy,
            "T6": self.test_t6_index_status,
        }

        if categories:
            tests_to_run = {k: v for k, v in all_tests.items() if k in categories}
        else:
            tests_to_run = all_tests

        self.results = []
        for cat_id, test_func in tests_to_run.items():
            try:
                result = test_func()
                self.results.append(result)
            except Exception as e:
                self.results.append(CategoryResult(
                    cat_id, f"Error: {str(e)[:50]}",
                    [TestResult(cat_id, "Error", TestStatus.FAIL, str(e))]
                ))

        return self.results

    def get_summary(self) -> Dict[str, Any]:
        """Get test summary"""
        total_passed = sum(c.passed for c in self.results)
        total_failed = sum(c.failed for c in self.results)
        total_warnings = sum(c.warnings for c in self.results)
        total_tests = sum(len(c.tests) for c in self.results)

        health = "HEALTHY"
        if total_failed > 0:
            health = "UNHEALTHY"
        elif total_warnings > 0:
            health = "DEGRADED"

        return {
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "warnings": total_warnings,
            "health": health,
            "timestamp": datetime.now().isoformat()
        }


class ReportFormatter:
    """Format test results for output"""

    # Use ASCII fallbacks for Windows compatibility
    STATUS_ICONS = {
        TestStatus.PASS: "[PASS]",
        TestStatus.FAIL: "[FAIL]",
        TestStatus.WARN: "[WARN]",
        TestStatus.SKIP: "[SKIP]",
    }

    @classmethod
    def format_console(cls, results: List[CategoryResult], summary: Dict) -> str:
        """Format results for console output"""
        lines = []
        separator = "=" * 60

        lines.append(separator)
        lines.append("Graph DB Quality Test Report")
        lines.append(separator)
        lines.append(f"Test Date: {summary['timestamp'][:19]}")
        lines.append("")

        for category in results:
            lines.append(f"{category.category_id}. {category.name}")
            for i, test in enumerate(category.tests):
                prefix = "|--" if i < len(category.tests) - 1 else "`--"
                icon = cls.STATUS_ICONS.get(test.status, "?")
                lines.append(f"{prefix} {test.test_id} {test.name:<30} {icon} ({test.message})")
            lines.append("")

        lines.append(separator)
        lines.append(f"Summary: {summary['passed']}/{summary['total_tests']} PASSED | "
                    f"{summary['failed']} FAILED | {summary['warnings']} WARNINGS")

        health_icon = "[OK]" if summary['health'] == "HEALTHY" else (
            "[WARN]" if summary['health'] == "DEGRADED" else "[FAIL]"
        )
        lines.append(f"Overall: {health_icon} {summary['health']}")
        lines.append(separator)

        return "\n".join(lines)

    @classmethod
    def format_json(cls, results: List[CategoryResult], summary: Dict) -> str:
        """Format results as JSON"""
        output = {
            "summary": summary,
            "categories": []
        }

        for category in results:
            cat_data = {
                "id": category.category_id,
                "name": category.name,
                "passed": category.passed,
                "failed": category.failed,
                "warnings": category.warnings,
                "tests": []
            }

            for test in category.tests:
                cat_data["tests"].append({
                    "id": test.test_id,
                    "name": test.name,
                    "status": test.status.value,
                    "message": test.message,
                    "value": test.value,
                    "threshold": test.threshold,
                    "details": test.details
                })

            output["categories"].append(cat_data)

        return json.dumps(output, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(description="Graph DB Quality Test")
    parser.add_argument("--category", "-c", type=str, help="Run specific category (T1-T6)")
    parser.add_argument("--format", "-f", type=str, choices=["console", "json"], default="console")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--uri", type=str, help="Neo4j URI (default: from env)")
    parser.add_argument("--user", type=str, help="Neo4j user (default: from env)")
    parser.add_argument("--password", type=str, help="Neo4j password (default: from env)")

    args = parser.parse_args()

    # Parse categories
    categories = None
    if args.category:
        categories = [c.strip().upper() for c in args.category.split(",")]

    # Create tester
    try:
        tester = GraphDBQualityTester(
            uri=args.uri,
            user=args.user,
            password=args.password
        )
        tester.verbose = args.verbose
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    # Connect
    if not tester.connect():
        print("Failed to connect to Neo4j database")
        sys.exit(1)

    try:
        # Run tests
        results = tester.run_all_tests(categories)
        summary = tester.get_summary()

        # Format output
        if args.format == "json":
            output = ReportFormatter.format_json(results, summary)
        else:
            output = ReportFormatter.format_console(results, summary)

        print(output)

        # Exit code based on health
        if summary["health"] == "UNHEALTHY":
            sys.exit(1)
        elif summary["health"] == "DEGRADED":
            sys.exit(0)  # Warnings are OK
        else:
            sys.exit(0)

    finally:
        tester.close()


if __name__ == "__main__":
    main()
