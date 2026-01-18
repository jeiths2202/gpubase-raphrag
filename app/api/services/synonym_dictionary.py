"""
Synonym Dictionary for RAG Search Enhancement

도메인 특화 동의어 사전으로 검색 품질 향상
- 기술 용어 변형 (VSAM, vsam, 비샘)
- 다국어 동의어 (OpenFrame, 오픈프레임)
- 약어 확장 (JCL, Job Control Language)
"""

import re
import logging
from typing import List, Set, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SynonymDictionary:
    """
    Domain-specific synonym dictionary for query expansion.

    Improves RAG search by:
    1. Expanding queries with synonyms
    2. Normalizing technical terms
    3. Handling multilingual variations
    """

    def __init__(self):
        # Bidirectional synonym groups
        # Each group contains terms that should match each other
        self._synonym_groups: List[Set[str]] = [
            # OpenFrame products
            {"openframe", "오픈프레임", "オープンフレーム", "open frame"},
            {"openframe base", "오픈프레임 베이스", "openframe-base"},
            {"openframe batch", "오픈프레임 배치", "openframe-batch"},
            {"openframe online", "오픈프레임 온라인", "openframe-online"},

            # VSAM related
            {"vsam", "비샘", "비쌤", "v-sam"},
            {"non-vsam", "nonvsam", "non vsam", "비vsam", "논vsam", "non-v-sam"},
            {"ksds", "key sequenced data set", "키순차데이터셋"},
            {"esds", "entry sequenced data set", "입력순차데이터셋"},
            {"rrds", "relative record data set", "상대레코드데이터셋"},

            # JCL related
            {"jcl", "job control language", "잡컨트롤랭귀지", "작업제어언어"},
            {"jcllib", "jcl library", "jcl 라이브러리"},
            {"proclib", "procedure library", "프로시저 라이브러리"},
            {"ddname", "dd name", "dd네임", "데이터정의명"},
            {"dsn", "dataset name", "dsname", "데이터셋명", "데이터셋이름"},

            # COBOL related
            {"cobol", "코볼", "コボル"},
            {"copybook", "카피북", "copy book", "コピーブック"},
            {"working-storage", "working storage", "워킹스토리지"},
            {"procedure division", "프로시저 디비전", "절차부"},

            # Database/Transaction
            {"cics", "씨익스", "시익스", "customer information control system"},
            {"ims", "아이엠에스", "information management system"},
            {"db2", "디비투", "database 2"},
            {"sql", "에스큐엘", "structured query language"},

            # Batch processing
            {"batch", "배치", "バッチ", "일괄처리"},
            {"job", "잡", "ジョブ", "작업"},
            {"step", "스텝", "ステップ", "단계"},
            {"abend", "에이벤드", "abnormal end", "비정상종료"},

            # Utilities
            {"sort", "소트", "ソート", "정렬"},
            {"merge", "머지", "マージ", "병합"},
            {"idcams", "아이디캠스", "access method services"},
            {"iebgener", "아이이비제너"},
            {"iebcopy", "아이이비카피"},

            # Error/Return codes
            {"return code", "리턴코드", "반환코드", "rc"},
            {"condition code", "컨디션코드", "조건코드", "cc"},
            {"abend code", "에이벤드코드", "비정상종료코드"},

            # System components
            {"jes", "jes2", "jes3", "job entry subsystem"},
            {"spool", "스풀", "スプール"},
            {"catalog", "카탈로그", "カタログ"},
            {"vtoc", "volume table of contents", "볼륨목차"},

            # Common operations
            {"install", "설치", "インストール", "installation"},
            {"configure", "설정", "구성", "configuration", "컨피그"},
            {"error", "에러", "오류", "エラー"},
            {"exception", "예외", "익셉션"},

            # File operations
            {"dataset", "데이터셋", "데이터세트", "data set", "データセット"},
            {"file", "파일", "ファイル"},
            {"record", "레코드", "レコード"},
            {"member", "멤버", "メンバー"},

            # Common terms
            {"overview", "개요", "概要", "소개", "introduction"},
            {"guide", "가이드", "ガイド", "안내"},
            {"reference", "레퍼런스", "リファレンス", "참조"},
            {"manual", "매뉴얼", "マニュアル", "설명서"},
        ]

        # Build lookup index: term -> group index
        self._term_to_group: Dict[str, int] = {}
        for group_idx, group in enumerate(self._synonym_groups):
            for term in group:
                self._term_to_group[term.lower()] = group_idx

        logger.info(f"[SynonymDictionary] Loaded {len(self._synonym_groups)} synonym groups, "
                   f"{len(self._term_to_group)} terms indexed")

    def get_synonyms(self, term: str) -> Set[str]:
        """
        Get all synonyms for a given term.

        Args:
            term: The term to look up

        Returns:
            Set of synonyms (including the original term)
        """
        term_lower = term.lower().strip()

        if term_lower in self._term_to_group:
            group_idx = self._term_to_group[term_lower]
            return self._synonym_groups[group_idx].copy()

        return {term}  # Return original if no synonyms found

    def expand_query(self, query: str) -> Tuple[str, List[str]]:
        """
        Expand a query with synonyms.

        Args:
            query: Original search query

        Returns:
            Tuple of (main_keyword, list of expanded terms)
        """
        query_lower = query.lower().strip()

        # Try to find exact match first
        if query_lower in self._term_to_group:
            synonyms = self.get_synonyms(query_lower)
            logger.info(f"[SynonymDictionary] Exact match: '{query}' -> {len(synonyms)} synonyms")
            return query, list(synonyms)

        # Try to find partial matches
        expanded_terms = set()
        matched_terms = []

        for term in self._term_to_group.keys():
            # Check if term is in query or query is in term
            if term in query_lower or query_lower in term:
                synonyms = self.get_synonyms(term)
                expanded_terms.update(synonyms)
                matched_terms.append(term)

        if expanded_terms:
            logger.info(f"[SynonymDictionary] Partial match: '{query}' matched {matched_terms}, "
                       f"expanded to {len(expanded_terms)} terms")
            return query, list(expanded_terms)

        # No synonyms found
        logger.debug(f"[SynonymDictionary] No synonyms for: '{query}'")
        return query, [query]

    def expand_for_sql_like(self, query: str) -> List[str]:
        """
        Expand query for SQL LIKE patterns.

        Returns list of terms suitable for:
        WHERE content LIKE '%term1%' OR content LIKE '%term2%'

        Args:
            query: Original search query

        Returns:
            List of terms for LIKE matching
        """
        _, expanded = self.expand_query(query)

        # Filter out very short terms to avoid too broad matches
        filtered = [t for t in expanded if len(t) >= 2]

        return filtered if filtered else [query]

    def normalize_term(self, term: str) -> str:
        """
        Normalize a term to its canonical form.

        Args:
            term: Term to normalize

        Returns:
            Canonical form of the term
        """
        term_lower = term.lower().strip()

        if term_lower in self._term_to_group:
            group_idx = self._term_to_group[term_lower]
            # Return first term in group as canonical
            return list(self._synonym_groups[group_idx])[0]

        return term

    def add_synonym_group(self, terms: List[str]) -> None:
        """
        Add a new synonym group dynamically.

        Args:
            terms: List of synonymous terms
        """
        if len(terms) < 2:
            return

        new_group = set(t.lower().strip() for t in terms)
        group_idx = len(self._synonym_groups)

        self._synonym_groups.append(new_group)
        for term in new_group:
            self._term_to_group[term] = group_idx

        logger.info(f"[SynonymDictionary] Added new group: {new_group}")


# Singleton instance
_synonym_dictionary: Optional[SynonymDictionary] = None


def get_synonym_dictionary() -> SynonymDictionary:
    """Get singleton SynonymDictionary instance."""
    global _synonym_dictionary
    if _synonym_dictionary is None:
        _synonym_dictionary = SynonymDictionary()
    return _synonym_dictionary
