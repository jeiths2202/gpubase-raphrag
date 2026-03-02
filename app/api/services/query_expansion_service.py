"""
Query Expansion Service
Expands queries with synonyms and related terms for better retrieval.
Supports Japanese, Korean, and English technical terms.

Synonyms can be loaded from:
1. MetadataConfigService (PostgreSQL) - primary
2. Fallback hardcoded dictionaries - when DB unavailable
"""
import re
import logging
from typing import List, Dict, Set, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# MetadataConfigService lazy import to avoid circular dependencies
_metadata_config_service = None
_metadata_loaded = False

async def _get_metadata_config_service():
    """Lazy load MetadataConfigService."""
    global _metadata_config_service
    if _metadata_config_service is None:
        try:
            from .metadata_config_service import get_metadata_config_service
            _metadata_config_service = await get_metadata_config_service()
            logger.info("MetadataConfigService loaded for QueryExpansionService")
        except Exception as e:
            logger.warning(f"Failed to load MetadataConfigService: {e}")
    return _metadata_config_service


@dataclass
class ExpandedQuery:
    """Result of query expansion"""
    original: str
    expanded_terms: List[str]
    all_terms: Set[str]
    language: str

    def get_expanded_query(self) -> str:
        """Get query with expanded terms for embedding"""
        # Combine original with key expanded terms
        if not self.expanded_terms:
            return self.original

        # Add top synonyms to the query for better embedding
        # Increased from 3 to 5 terms to include cross-language translations
        expanded = f"{self.original} {' '.join(self.expanded_terms[:5])}"
        return expanded


class QueryExpansionService:
    """
    Service for expanding queries with synonyms and related terms.

    Improves RAG retrieval by:
    1. Adding Japanese synonyms (処理手順 → 処理順序, 手順, フロー)
    2. Adding Korean synonyms (처리절차 → 처리순서, 절차)
    3. Adding English variations (procedure → process, steps, flow)
    4. Technical term expansion (MFS → Message Format Service)
    """

    # Japanese synonym mappings
    JA_SYNONYMS: Dict[str, List[str]] = {
        # Process/Procedure related
        "処理手順": ["処理順序", "処理フロー", "処理の流れ", "手順", "順序"],
        "処理順序": ["処理手順", "処理フロー", "処理の流れ", "手順", "順序"],
        "手順": ["順序", "ステップ", "フロー", "流れ", "プロセス"],
        "順序": ["手順", "ステップ", "フロー", "流れ", "順番"],
        "フロー": ["流れ", "手順", "プロセス", "順序"],
        "流れ": ["フロー", "手順", "プロセス", "順序"],

        # Structure related
        "構造": ["構成", "アーキテクチャ", "仕組み"],
        "構成": ["構造", "アーキテクチャ", "仕組み"],
        "仕組み": ["構造", "構成", "メカニズム"],

        # Function related
        "機能": ["機能一覧", "特徴", "機能説明"],
        "概要": ["概略", "要約", "サマリー", "説明"],

        # Definition related
        "定義": ["定義方法", "定義手順", "設定"],
        "設定": ["設定方法", "設定手順", "コンフィグ"],

        # Error related
        "エラー": ["障害", "問題", "トラブル", "異常"],
        "障害": ["エラー", "問題", "トラブル", "異常"],
    }

    # Korean synonym mappings
    KO_SYNONYMS: Dict[str, List[str]] = {
        "처리절차": ["처리순서", "처리흐름", "처리과정", "절차", "순서"],
        "처리순서": ["처리절차", "처리흐름", "처리과정", "절차", "순서"],
        "절차": ["순서", "단계", "흐름", "과정"],
        "순서": ["절차", "단계", "흐름", "과정"],
        "구조": ["구성", "아키텍처", "체계"],
        "기능": ["기능목록", "특징", "기능설명"],
        "개요": ["요약", "설명", "소개"],
        "오류": ["에러", "문제", "장애"],
    }

    # English synonym mappings
    EN_SYNONYMS: Dict[str, List[str]] = {
        "procedure": ["process", "steps", "flow", "sequence", "workflow"],
        "process": ["procedure", "steps", "flow", "sequence", "workflow"],
        "flow": ["process", "procedure", "sequence", "workflow"],
        "structure": ["architecture", "composition", "organization"],
        "function": ["feature", "capability", "functionality"],
        "overview": ["summary", "introduction", "description"],
        "error": ["issue", "problem", "failure", "fault"],
    }

    # Technical term expansions (product-specific)
    TECHNICAL_TERMS: Dict[str, List[str]] = {
        # MFS - Message Format Service (IMS)
        "MFS": ["Message Format Service", "MFSメッセージフォーマット", "MFS処理", "MFSマップ", "MFS맵"],
        "MID": ["Message Input Descriptor", "MIDメッセージ入力記述子"],
        "MOD": ["Message Output Descriptor", "MODメッセージ出力記述子"],
        "DOF": ["Device Output Format", "DOFデバイス出力フォーマット"],
        "DIF": ["Device Input Format", "DIFデバイス入力フォーマット"],
        # BMS - Basic Mapping Support (CICS)
        "BMS": ["Basic Mapping Support", "BMSマップ", "BMS맵", "マッピングサポート",
                "BMSマクロ", "シンボリックマップ", "物理マップ", "Mapping Support"],
        # IMS related
        "IMS": ["Information Management System", "IMSシステム", "IMS/DC"],
        "BMP": ["Batch Message Processing", "BMPバッチ処理", "BMPユーザーサーバー"],
        "MPP": ["Message Processing Program", "MPPプログラム", "MPPユーザーサーバー"],
        "PSB": ["Program Specification Block", "PSBプログラム仕様ブロック"],
        "DBD": ["Database Description", "DBDデータベース記述"],
        # CICS/OSC related
        "OSC": ["Online Service Controller", "OSCシステム", "OSCアプリケーション"],
        "CICS": ["Customer Information Control System", "CICSシステム", "CICS/TS"],
        # Map related terms
        "맵": ["マップ", "MAP", "map"],
        "MAP": ["マップ", "맵", "map"],
        "マップ": ["MAP", "맵", "map"],
    }

    # Korean to Japanese cross-language mappings for improved retrieval
    KO_TO_JA_MAPPINGS: Dict[str, List[str]] = {
        # Common technical terms
        "맵": ["マップ", "MAP"],
        "특징": ["特徴", "特性"],
        "비교": ["比較"],
        "설명": ["説明", "解説"],
        "알려": ["教えて", "説明して"],
        "기능": ["機能", "機能説明"],
        "구조": ["構造", "構成"],
        "처리": ["処理"],
        "정의": ["定義"],
        "설정": ["設定"],
        "오류": ["エラー", "障害"],
        "에러": ["エラー", "障害"],
        "개요": ["概要", "概略"],
        "사용법": ["使用方法", "使い方"],
        "사용": ["使用", "利用"],
        "방법": ["方法", "やり方"],
        "예제": ["例", "サンプル"],
        "문서": ["ドキュメント", "文書"],
        "가이드": ["ガイド", "Guide"],
        "참조": ["参照", "リファレンス"],
    }

    def __init__(self):
        """Initialize the query expansion service"""
        # Build reverse mappings for efficiency using fallback dictionaries
        self._ja_all_synonyms = self._build_synonym_groups(self.JA_SYNONYMS)
        self._ko_all_synonyms = self._build_synonym_groups(self.KO_SYNONYMS)
        self._en_all_synonyms = self._build_synonym_groups(self.EN_SYNONYMS)
        self._metadata_loaded = False

    async def load_synonyms_from_db(self) -> bool:
        """
        Load synonyms from MetadataConfigService (PostgreSQL).
        Call this once before using the service for DB-driven synonyms.

        Returns:
            True if successfully loaded, False otherwise
        """
        global _metadata_loaded
        if self._metadata_loaded or _metadata_loaded:
            return True

        try:
            metadata_service = await _get_metadata_config_service()
            if not metadata_service:
                return False

            # Load Japanese synonyms
            ja_synonyms = await metadata_service.get_all_synonyms(language="ja")
            if ja_synonyms:
                for base_term, synonym_list in ja_synonyms.items():
                    if base_term not in self.JA_SYNONYMS:
                        self.JA_SYNONYMS[base_term] = []
                    for syn in synonym_list:
                        if syn not in self.JA_SYNONYMS[base_term]:
                            self.JA_SYNONYMS[base_term].append(syn)
                logger.debug(f"Loaded {len(ja_synonyms)} Japanese synonym groups from DB")

            # Load Korean synonyms
            ko_synonyms = await metadata_service.get_all_synonyms(language="ko")
            if ko_synonyms:
                for base_term, synonym_list in ko_synonyms.items():
                    if base_term not in self.KO_SYNONYMS:
                        self.KO_SYNONYMS[base_term] = []
                    for syn in synonym_list:
                        if syn not in self.KO_SYNONYMS[base_term]:
                            self.KO_SYNONYMS[base_term].append(syn)
                logger.debug(f"Loaded {len(ko_synonyms)} Korean synonym groups from DB")

            # Load English synonyms
            en_synonyms = await metadata_service.get_all_synonyms(language="en")
            if en_synonyms:
                for base_term, synonym_list in en_synonyms.items():
                    if base_term not in self.EN_SYNONYMS:
                        self.EN_SYNONYMS[base_term] = []
                    for syn in synonym_list:
                        if syn not in self.EN_SYNONYMS[base_term]:
                            self.EN_SYNONYMS[base_term].append(syn)
                logger.debug(f"Loaded {len(en_synonyms)} English synonym groups from DB")

            # Rebuild synonym groups with new data
            self._ja_all_synonyms = self._build_synonym_groups(self.JA_SYNONYMS)
            self._ko_all_synonyms = self._build_synonym_groups(self.KO_SYNONYMS)
            self._en_all_synonyms = self._build_synonym_groups(self.EN_SYNONYMS)

            self._metadata_loaded = True
            _metadata_loaded = True
            logger.info("Synonyms loaded from MetadataConfigService")
            return True

        except Exception as e:
            logger.warning(f"Failed to load synonyms from DB: {e}")
            return False

    def _build_synonym_groups(self, synonyms: Dict[str, List[str]]) -> Dict[str, Set[str]]:
        """Build complete synonym groups (A→B means B→A too)"""
        groups: Dict[str, Set[str]] = {}

        for term, related in synonyms.items():
            # Add all related terms for this term
            if term not in groups:
                groups[term] = set()
            groups[term].update(related)

            # Add reverse mappings
            for r in related:
                if r not in groups:
                    groups[r] = set()
                groups[r].add(term)
                groups[r].update(t for t in related if t != r)

        return groups

    async def expand_async(self, query: str, language: str = "auto") -> ExpandedQuery:
        """
        Expand a query with synonyms and related terms (async version).
        Loads synonyms from DB on first call.

        Args:
            query: Original query text
            language: Language code (ja, ko, en, auto)

        Returns:
            ExpandedQuery with original and expanded terms
        """
        # Load synonyms from DB on first call
        if not self._metadata_loaded:
            await self.load_synonyms_from_db()

        return self.expand(query, language)

    def expand(self, query: str, language: str = "auto") -> ExpandedQuery:
        """
        Expand a query with synonyms and related terms (sync version).
        Uses current synonym dictionaries (DB or fallback).

        Args:
            query: Original query text
            language: Language code (ja, ko, en, auto)

        Returns:
            ExpandedQuery with original and expanded terms
        """
        if language == "auto":
            language = self._detect_language(query)

        expanded_terms: List[str] = []
        all_terms: Set[str] = {query}

        # Add language-specific synonyms
        if language == "ja":
            expanded_terms.extend(self._expand_japanese(query))
        elif language == "ko":
            expanded_terms.extend(self._expand_korean(query))
            # Add Japanese translations for Korean queries (cross-language retrieval)
            expanded_terms.extend(self._expand_cross_language(query, "ko"))
        else:
            expanded_terms.extend(self._expand_english(query))

        # Add technical term expansions (language-agnostic)
        expanded_terms.extend(self._expand_technical(query))

        # Remove duplicates while preserving order
        seen = {query}
        unique_terms = []
        for term in expanded_terms:
            if term not in seen:
                seen.add(term)
                unique_terms.append(term)

        all_terms.update(unique_terms)

        logger.debug(f"Query expansion: '{query}' -> {unique_terms[:5]}...")

        return ExpandedQuery(
            original=query,
            expanded_terms=unique_terms,
            all_terms=all_terms,
            language=language
        )

    def _detect_language(self, text: str) -> str:
        """Detect language from text"""
        # Check for Japanese characters (Hiragana, Katakana, Kanji)
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text):
            # Check if it's more likely Korean (Hangul)
            if re.search(r'[\uac00-\ud7af]', text):
                return "ko"
            return "ja"

        # Check for Korean characters
        if re.search(r'[\uac00-\ud7af]', text):
            return "ko"

        return "en"

    def _expand_japanese(self, query: str) -> List[str]:
        """Expand Japanese query with synonyms"""
        expanded = []

        for term, synonyms in self._ja_all_synonyms.items():
            if term in query:
                expanded.extend(synonyms)

        return expanded

    def _expand_korean(self, query: str) -> List[str]:
        """Expand Korean query with synonyms"""
        expanded = []

        for term, synonyms in self._ko_all_synonyms.items():
            if term in query:
                expanded.extend(synonyms)

        return expanded

    def _expand_cross_language(self, query: str, source_lang: str) -> List[str]:
        """
        Expand query with cross-language translations.
        Particularly useful for Korean→Japanese retrieval when documents are in Japanese.

        Args:
            query: Original query text
            source_lang: Detected source language

        Returns:
            List of translated/equivalent terms in target languages
        """
        expanded = []

        if source_lang == "ko":
            # Korean to Japanese expansion
            for ko_term, ja_terms in self.KO_TO_JA_MAPPINGS.items():
                if ko_term in query:
                    expanded.extend(ja_terms)

        return expanded

    def _expand_english(self, query: str) -> List[str]:
        """Expand English query with synonyms"""
        expanded = []
        query_lower = query.lower()

        for term, synonyms in self._en_all_synonyms.items():
            if term.lower() in query_lower:
                expanded.extend(synonyms)

        return expanded

    def _expand_technical(self, query: str) -> List[str]:
        """Expand technical terms"""
        expanded = []
        query_upper = query.upper()

        for term, expansions in self.TECHNICAL_TERMS.items():
            if term in query_upper:
                expanded.extend(expansions)

        return expanded


# Singleton instance
_service: Optional[QueryExpansionService] = None


def get_query_expansion_service() -> QueryExpansionService:
    """Get or create QueryExpansionService instance (sync version)."""
    global _service
    if _service is None:
        _service = QueryExpansionService()
    return _service


async def get_query_expansion_service_async() -> QueryExpansionService:
    """Get or create QueryExpansionService instance with DB synonyms loaded (async version)."""
    global _service
    if _service is None:
        _service = QueryExpansionService()
        await _service.load_synonyms_from_db()
    elif not _service._metadata_loaded:
        await _service.load_synonyms_from_db()
    return _service
