"""
Product Router Service

쿼리를 적절한 제품으로 라우팅하는 서비스.
키워드 기반 분류 및 confidence 점수 계산을 수행합니다.
"""
import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from ..models.openframe_rag import (
    ProductId,
    ClassificationResult,
    ProductKeywords,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Product Keyword Definitions
# =============================================================================

@dataclass
class ProductConfig:
    """Product configuration with keywords and patterns"""
    product: ProductId
    keywords: List[str]
    patterns: List[str]  # Regex patterns
    weight: float = 1.0


# 제품별 키워드 정의
PRODUCT_CONFIGS: List[ProductConfig] = [
    ProductConfig(
        product=ProductId.OPENFRAME_MVS,
        keywords=[
            # TJES 관련
            "tjes", "tjesmgr", "tjclrun", "jeslog", "tjesmgr", "job entry",
            # JCL 관련
            "jcl", "jclrun", "jesrun", "job", "dd", "exec", "proc", "steplib",
            # MVS 유틸리티
            "idcams", "iebgener", "iebcopy", "iebupdte", "iehprogm",
            "dfsort", "syncsort", "icetool",
            # TACF 관련
            "tacf", "tacfmgr", "racf", "security",
            # 시스템 관리
            "tmboot", "tmdown", "ofboot", "ofdown", "jesinit", "jesdown",
            # OSC 관련
            "osc", "oscmgr", "cics", "online",
            # OSI 관련
            "osi", "osimgr",
            # HiDB 관련 (階層型データベース)
            "hidb", "hidbmgr", "ims", "dl/i", "dli",
            "階層データベース", "階層型データベース", "階層db",
            "dbpcb", "psbgen", "dbd", "psb", "pcb",
            # NDB 관련
            "ndb", "ndbmgr",
            # 기타 MVS
            "mvs", "mainframe", "batch", "spufi", "ispf",
        ],
        patterns=[
            r"tjesmgr\s+\w+",      # tjesmgr 명령어
            r"tacfmgr\s+\w+",      # tacfmgr 명령어
            r"oscmgr\s+\w+",       # oscmgr 명령어
            r"osimgr\s+\w+",       # osimgr 명령어
            r"hidbmgr\s+\w+",      # hidbmgr 명령어
            r"ndbmgr\s+\w+",       # ndbmgr 명령어
            r"\/\/\w+\s+JOB",      # JCL JOB statement
            r"EXEC\s+PGM=",        # JCL EXEC statement
            r"DD\s+DSN=",          # JCL DD statement
            r"-\d{4,5}",           # 에러 코드 패턴
            r"ABEND\s+S\d{3}",     # ABEND 코드
        ],
        weight=1.2  # MVS는 가장 일반적이므로 약간 높은 가중치
    ),
    ProductConfig(
        product=ProductId.MSP_OPENFRAME,
        keywords=[
            "msp", "msp openframe", "msp-openframe",
            "jes2", "jes3", "sms", "hsm", "dfhsm",
        ],
        patterns=[
            r"msp\s+\w+",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.VOS3_OPENFRAME,
        keywords=[
            "vos3", "vos3 openframe", "vos3-openframe",
            "acos", "nec", "日立",
        ],
        patterns=[
            r"vos3\s+\w+",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OPENFRAME_BASE,
        keywords=[
            # Base 시스템 키워드
            "base", "openframe base", "openframe/base", "of_base",
            # 데이터셋 관련
            "dataset", "dsalc", "dsorg", "recfm", "lrecl", "blksize",
            "vsam", "ksds", "esds", "rrds", "lds",
            # 카탈로그 관련
            "catalog", "catmgr", "alias", "gdg", "generation",
            # 볼륨 관련
            "volume", "volser", "vtoc", "dscb",
            # 파일 시스템
            "pds", "pdse", "sequential", "partitioned",
            # 유틸리티
            "dsmigin", "dsmigout", "listcat", "define",
        ],
        patterns=[
            r"base\s+system",
            r"openframe\s*/?\s*base",
            r"dsalc_\w+",          # DSALC 에러 코드
            r"VSAM\s+\w+",
            r"GDG\s+\w+",
        ],
        weight=1.1  # Base는 일반적인 질문이므로 약간 높은 가중치
    ),
    ProductConfig(
        product=ProductId.TIBERO7,
        keywords=[
            "tibero", "tibero7", "tibero 7", "tbsql", "tbcli",
            "tbdsn", "tbexport", "tbimport", "tbloader",
            "tsql", "tac", "taf", "tbadmin",
            # SQL 관련
            "sql", "oracle", "database", "db",
            "select", "insert", "update", "delete",
            "pl/sql", "procedure", "function", "trigger",
            # DBMS 패키지/기능
            "dbms_lock", "dbms_output", "dbms_sql", "dbms_job",
            "dbms_scheduler", "dbms_metadata", "dbms_stats",
            "dbms_", "package", "パッケージ",
            # tbPSM 관련
            "tbpsm", "psm", "stored procedure",
        ],
        patterns=[
            r"tibero\s*\d*",
            r"tb\w+",              # tb로 시작하는 명령어
            r"SELECT\s+.+\s+FROM", # SQL SELECT
            r"dbms_\w+",           # DBMS_* パッケージ
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OFASM,
        keywords=[
            "ofasm", "assembler", "asm", "macro",
            "hlasm", "assembler language",
            "csect", "dsect", "using", "balr",
        ],
        patterns=[
            r"ofasm\s+\w+",
            r"CSECT|DSECT|USING|BALR",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OFCOBOL,
        keywords=[
            "ofcobol", "cobol", "cobc", "cobrun",
            "copybook", "working-storage", "procedure division",
            "file section", "data division",
            "perform", "move", "compute",
        ],
        patterns=[
            r"ofcobol\s+\w+",
            r"WORKING-STORAGE\s+SECTION",
            r"PROCEDURE\s+DIVISION",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.XSP_OPENFRAME,
        keywords=[
            "xsp", "xsp openframe", "xsp-openframe",
            "transaction", "tp", "온라인",
        ],
        patterns=[
            r"xsp\s+\w+",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.TMAX,
        keywords=[
            "tmax", "tuxedo", "tmaxsoft",
            "tpacall", "tpcall", "tpreturn",
            "domain", "svrgroup", "server",
            "config", "ulog", "gwtdomain",
        ],
        patterns=[
            r"tmax\s+\w+",
            r"tp\w+",             # tp로 시작하는 함수
        ],
        weight=1.0
    ),
]

# Pre-compile patterns
for config in PRODUCT_CONFIGS:
    config._compiled_patterns = [
        re.compile(p, re.IGNORECASE) for p in config.patterns
    ]


class ProductRouterService:
    """
    Product Router Service

    쿼리를 분석하여 적절한 제품으로 라우팅합니다.
    키워드 매칭 및 패턴 매칭을 통해 confidence 점수를 계산합니다.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        min_keyword_matches: int = 1,
    ):
        """
        Initialize service

        Args:
            confidence_threshold: 자동 라우팅을 위한 최소 confidence (기본: 0.7)
            min_keyword_matches: 최소 매칭 키워드 수 (기본: 1)
        """
        self.confidence_threshold = confidence_threshold
        self.min_keyword_matches = min_keyword_matches
        self.product_configs = PRODUCT_CONFIGS

    def classify(self, query: str) -> ClassificationResult:
        """
        쿼리를 분석하여 제품 분류 결과 반환

        Args:
            query: 사용자 쿼리

        Returns:
            ClassificationResult with product, confidence, and suggestions
        """
        query_lower = query.lower()
        scores: Dict[ProductId, float] = {}
        matched_keywords: Dict[ProductId, List[str]] = {}

        for config in self.product_configs:
            score, matches = self._calculate_score(query_lower, config)
            if score > 0:
                scores[config.product] = score
                matched_keywords[config.product] = matches

        # Sort by score
        sorted_products = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        if not sorted_products:
            # No matches found
            return ClassificationResult(
                product=ProductId.OTHER,
                confidence=0.0,
                needs_selection=True,
                suggestions=[ProductId.OPENFRAME_MVS.value],  # Default suggestion
                matched_keywords=[],
                all_scores={},
            )

        # Get top result
        top_product, top_score = sorted_products[0]

        # Normalize score to 0-1 range
        # Typical strong match: 3-5 keywords (0.3-0.5) + 1-2 patterns (0.2-0.4) + bonus (1.2) ≈ 0.6-1.2
        max_score = 1.5
        confidence = min(top_score / max_score, 1.0)

        # Determine if user selection is needed
        needs_selection = confidence < self.confidence_threshold

        # Get suggestions (top 3 products)
        suggestions = [p.value for p, _ in sorted_products[:3]]

        # All scores for transparency
        all_scores = {p.value: round(s / max_score, 3) for p, s in scores.items()}

        return ClassificationResult(
            product=top_product,
            confidence=round(confidence, 3),
            needs_selection=needs_selection,
            suggestions=suggestions,
            matched_keywords=matched_keywords.get(top_product, []),
            all_scores=all_scores,
        )

    def _calculate_score(
        self,
        query_lower: str,
        config: ProductConfig
    ) -> Tuple[float, List[str]]:
        """
        Calculate score for a product

        Args:
            query_lower: Lowercase query
            config: Product configuration

        Returns:
            (score, matched_keywords)
        """
        score = 0.0
        matched = []

        # Keyword matching
        for keyword in config.keywords:
            if keyword.lower() in query_lower:
                score += 0.15 * config.weight
                matched.append(keyword)

        # Pattern matching (higher weight)
        for pattern in getattr(config, '_compiled_patterns', []):
            if pattern.search(query_lower):
                score += 0.3 * config.weight
                matched.append(f"pattern:{pattern.pattern[:20]}")

        # Bonus for multiple matches
        if len(matched) >= 3:
            score *= 1.2
        elif len(matched) >= 2:
            score *= 1.1

        return score, matched

    def get_product_keywords(self, product: ProductId) -> List[str]:
        """Get keywords for a specific product"""
        for config in self.product_configs:
            if config.product == product:
                return config.keywords
        return []

    def get_all_products(self) -> List[ProductId]:
        """Get all supported products"""
        return [config.product for config in self.product_configs]


# =============================================================================
# Singleton Instance
# =============================================================================

_product_router_service: Optional[ProductRouterService] = None


def get_product_router_service() -> ProductRouterService:
    """Get Product Router service singleton"""
    global _product_router_service
    if _product_router_service is None:
        _product_router_service = ProductRouterService()
    return _product_router_service
