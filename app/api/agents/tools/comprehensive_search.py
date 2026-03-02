"""
Comprehensive Search Tool
키워드에 대한 통계, 문서 분포, 엔티티, 샘플을 병렬로 수집하여
Claude Code 스타일의 종합 답변을 생성합니다.
"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import asyncio
import logging
import re
from jinja2 import Template

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


class ComprehensiveSearchInput(BaseModel):
    """Comprehensive search input schema"""
    query: str = Field(description="검색 키워드 (예: IDCAMS, tjesmgr)")
    include_stats: bool = Field(default=True, description="통계 포함 여부")
    include_distribution: bool = Field(default=True, description="문서 분포 포함")
    include_samples: bool = Field(default=True, description="샘플 콘텐츠 포함")
    max_documents: int = Field(default=10, description="최대 문서 수")
    max_samples: int = Field(default=5, description="최대 샘플 수")


class ComprehensiveSearchResult(BaseModel):
    """Comprehensive search result schema"""
    keyword: str
    statistics: Dict[str, Any]
    document_distribution: List[Dict[str, Any]]
    entities: List[Dict[str, Any]]
    samples: List[Dict[str, Any]]
    formatted_output: str


# Jinja2 템플릿
COMPREHENSIVE_TEMPLATE = """## 🔍 {{ keyword }} 검색 결과

### 📊 검색 통계
| 항목 | 결과 |
|------|------|
{% for key, value in stats.items() %}| **{{ key }}** | {{ value }} |
{% endfor %}

{% if documents %}
### 📄 주요 문서 ({{ keyword }} 언급 횟수 Top {{ documents|length }})
| 문서명 | 언급 횟수 |
|--------|-----------|
{% for doc in documents %}| {{ doc.filename }} | {{ doc.count }}회 |
{% endfor %}
{% endif %}

{% if samples %}
### 📝 {{ keyword }} 주요 내용 샘플
{% for sample in samples %}
**{{ loop.index }}.** {% if sample.page_number %}(Page {{ sample.page_number }}){% endif %}
```
{{ sample.content[:500] }}{% if sample.content|length > 500 %}...{% endif %}
```
{% endfor %}
{% endif %}

### 🎯 결론
{{ conclusion }}
"""

# 결과가 없을 때 템플릿
NO_RESULT_TEMPLATE = """## 🔍 {{ keyword }} 검색 결과

### ⚠️ 검색 결과 없음

**{{ keyword }}**에 대한 정보를 지식 베이스에서 찾을 수 없습니다.

다음을 확인해 주세요:
- 키워드 철자가 정확한지 확인
- 관련 문서가 업로드되어 있는지 확인
- 다른 관련 키워드로 검색 시도
"""


class ComprehensiveSearchTool(BaseTool):
    """
    종합 검색 도구

    키워드에 대한 통계, 문서 분포, 엔티티, 샘플을 병렬로 수집하고
    마크다운 형식으로 포맷팅하여 반환합니다.
    """

    def __init__(self):
        super().__init__(
            name="comprehensive_search",
            description=(
                "Search for comprehensive information about a keyword including "
                "statistics, document distribution, entities, and content samples. "
                "Use this for queries like 'Tell me about X', 'What is X?', "
                "'X에 대해 알려줘', 'Xについて教えて'."
            )
        )
        self._template = None
        self._no_result_template = None

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색 키워드 (예: IDCAMS, tjesmgr)"
                },
                "include_stats": {
                    "type": "boolean",
                    "description": "통계 포함 여부",
                    "default": True
                },
                "include_distribution": {
                    "type": "boolean",
                    "description": "문서 분포 포함",
                    "default": True
                },
                "include_samples": {
                    "type": "boolean",
                    "description": "샘플 콘텐츠 포함",
                    "default": True
                },
                "max_documents": {
                    "type": "integer",
                    "description": "최대 문서 수",
                    "default": 10
                },
                "max_samples": {
                    "type": "integer",
                    "description": "최대 샘플 수",
                    "default": 5
                }
            },
            "required": ["query"]
        }

    @property
    def template(self) -> Template:
        """Jinja2 template lazy initialization"""
        if self._template is None:
            self._template = Template(COMPREHENSIVE_TEMPLATE)
        return self._template

    @property
    def no_result_template(self) -> Template:
        """No result template lazy initialization"""
        if self._no_result_template is None:
            self._no_result_template = Template(NO_RESULT_TEMPLATE)
        return self._no_result_template

    def _get_neo4j_driver(self):
        """Neo4j driver 획득"""
        import os
        from neo4j import GraphDatabase

        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "")

        return GraphDatabase.driver(uri, auth=(user, password))

    async def execute(
        self,
        context: AgentContext,
        query: str = "",
        include_stats: bool = True,
        include_distribution: bool = True,
        include_samples: bool = True,
        max_documents: int = 10,
        max_samples: int = 5,
        **kwargs
    ) -> ToolResult:
        """Execute comprehensive search"""
        if not query:
            return self.create_error_result("Query is required")

        keyword = self._extract_keyword(query)
        logger.info(f"[ComprehensiveSearch] Extracted keyword: '{keyword}' from query: '{query}'")

        try:
            # 병렬 쿼리 실행
            tasks = []
            task_names = []

            if include_stats:
                tasks.append(self._search_statistics(keyword))
                task_names.append("statistics")
                tasks.append(self._search_entities(keyword))
                task_names.append("entities")

            if include_distribution:
                tasks.append(self._get_document_distribution(keyword, max_documents))
                task_names.append("distribution")

            if include_samples:
                tasks.append(self._get_content_samples(keyword, max_samples))
                task_names.append("samples")
                tasks.append(self._get_entity_chunk_relations(keyword, max_samples))
                task_names.append("entity_samples")

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 결과 집계
            aggregated = self._aggregate_results(
                results, task_names, include_stats, include_distribution, include_samples
            )

            # 결과가 없는 경우 처리
            stats = aggregated.get("statistics", {})
            if stats.get("chunk_count", 0) == 0 and not aggregated.get("document_distribution"):
                formatted = self.no_result_template.render(keyword=keyword)
                return self.create_success_result(formatted)

            # 포맷팅
            formatted = self._format_results(keyword, aggregated, context)

            return self.create_success_result(formatted)

        except Exception as e:
            logger.error(f"[ComprehensiveSearch] Error: {e}", exc_info=True)
            return self.create_error_result(f"Comprehensive search error: {str(e)}")

    def _extract_keyword(self, query: str) -> str:
        """쿼리에서 키워드 추출"""
        patterns = [
            # Korean patterns
            r"(.+?)(?:에 대해|가 뭐|를 알려|이 뭐|란 뭐)",
            # Japanese patterns - specific action patterns first
            r"(.+?)(?:を実行|を使用|を起動|を停止|を設定|の注意|の使い方|の実行方法)",
            r"(.+?)(?:について|とは|って何|を教えて)",
            # English patterns
            r"(?:what is|tell me about|explain|describe)\s+(.+?)(?:\?|$)",
            r"(?:how to use|how to run|when running)\s+(.+?)(?:\?|$)",
            r"^(.+?)(?:\s+검색|\s+찾아|\s+알려)",
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                # 첫 번째 또는 마지막 그룹에서 키워드 추출
                keyword = match.group(1).strip()
                # 불필요한 문자 제거
                keyword = re.sub(r'[?？。、，]', '', keyword).strip()
                if keyword:
                    return keyword

        # 패턴 매칭 실패 시 원본 쿼리 정리
        cleaned = re.sub(r'[?？。、，]', '', query).strip()
        return cleaned

    async def _search_statistics(self, keyword: str) -> Dict[str, Any]:
        """통계 검색: Chunk 수, Entity 수"""
        driver = self._get_neo4j_driver()
        try:
            with driver.session() as session:
                # Chunk 수 쿼리
                chunk_result = session.run(
                    "MATCH (c:Chunk) WHERE c.content CONTAINS $keyword "
                    "RETURN count(c) as chunk_count",
                    keyword=keyword
                )
                chunk_record = chunk_result.single()
                chunk_count = chunk_record["chunk_count"] if chunk_record else 0

                # Entity 수 쿼리
                entity_result = session.run(
                    "MATCH (e:Entity) "
                    "WHERE e.name CONTAINS $keyword OR toLower(e.name) CONTAINS toLower($keyword) "
                    "RETURN count(e) as entity_count",
                    keyword=keyword
                )
                entity_record = entity_result.single()
                entity_count = entity_record["entity_count"] if entity_record else 0

                return {
                    "chunk_count": chunk_count,
                    "entity_count": entity_count,
                }
        finally:
            driver.close()

    async def _search_entities(self, keyword: str) -> List[Dict[str, Any]]:
        """엔티티 검색"""
        driver = self._get_neo4j_driver()
        try:
            with driver.session() as session:
                result = session.run(
                    "MATCH (e:Entity) "
                    "WHERE e.name CONTAINS $keyword OR toLower(e.name) CONTAINS toLower($keyword) "
                    "RETURN e.name as name, e.type as type "
                    "LIMIT 10",
                    keyword=keyword
                )
                return [dict(record) for record in result]
        finally:
            driver.close()

    async def _get_document_distribution(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        """문서별 언급 횟수 분포"""
        driver = self._get_neo4j_driver()
        try:
            with driver.session() as session:
                result = session.run(
                    "MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk) "
                    "WHERE c.content CONTAINS $keyword "
                    "RETURN d.filename as filename, count(c) as count "
                    "ORDER BY count DESC "
                    "LIMIT $limit",
                    keyword=keyword,
                    limit=limit
                )
                return [dict(record) for record in result]
        finally:
            driver.close()

    async def _get_content_samples(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        """샘플 콘텐츠 추출"""
        driver = self._get_neo4j_driver()
        try:
            with driver.session() as session:
                result = session.run(
                    "MATCH (c:Chunk) "
                    "WHERE c.content CONTAINS $keyword "
                    "RETURN c.content as content, c.page_number as page_number, c.id as chunk_id "
                    "LIMIT $limit",
                    keyword=keyword,
                    limit=limit
                )
                return [dict(record) for record in result]
        finally:
            driver.close()

    async def _get_entity_chunk_relations(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        """Entity-Chunk 관계 기반 샘플"""
        driver = self._get_neo4j_driver()
        try:
            with driver.session() as session:
                result = session.run(
                    "MATCH (e:Entity)-[r:MENTIONS]-(c:Chunk) "
                    "WHERE e.name = $keyword OR toLower(e.name) = toLower($keyword) "
                    "RETURN c.content as content, c.id as chunk_id, e.name as entity_name "
                    "LIMIT $limit",
                    keyword=keyword,
                    limit=limit
                )
                return [dict(record) for record in result]
        finally:
            driver.close()

    def _aggregate_results(
        self,
        results: List[Any],
        task_names: List[str],
        include_stats: bool,
        include_distribution: bool,
        include_samples: bool
    ) -> Dict[str, Any]:
        """결과 집계"""
        aggregated = {
            "statistics": {},
            "entities": [],
            "document_distribution": [],
            "samples": [],
            "entity_samples": [],
        }

        for i, name in enumerate(task_names):
            if i >= len(results):
                break

            result = results[i]
            if isinstance(result, Exception):
                logger.warning(f"[ComprehensiveSearch] Task '{name}' failed: {result}")
                continue

            if name == "statistics":
                aggregated["statistics"] = result
            elif name == "entities":
                aggregated["entities"] = result
            elif name == "distribution":
                aggregated["document_distribution"] = result
            elif name == "samples":
                aggregated["samples"] = result
            elif name == "entity_samples":
                aggregated["entity_samples"] = result

        return aggregated

    def _format_results(
        self,
        keyword: str,
        aggregated: Dict[str, Any],
        context: AgentContext
    ) -> str:
        """Jinja2 템플릿으로 결과 포맷팅"""
        stats = aggregated.get("statistics", {})
        entities = aggregated.get("entities", [])
        docs = aggregated.get("document_distribution", [])
        samples = aggregated.get("samples", [])
        entity_samples = aggregated.get("entity_samples", [])

        # 총 문서 수 계산
        doc_count = len(docs)

        # 엔티티 타입 요약
        entity_types = {}
        for e in entities:
            t = e.get("type", "UNKNOWN")
            entity_types[t] = entity_types.get(t, 0) + 1
        entity_summary = ", ".join(f"{t}({c})" for t, c in entity_types.items()) or "없음"

        # 샘플 결합 (중복 제거)
        all_samples = samples + entity_samples
        seen_ids = set()
        unique_samples = []
        for s in all_samples:
            sid = s.get("chunk_id")
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                unique_samples.append(s)

        # 결론 생성
        conclusion = self._generate_conclusion(keyword, stats, docs, context)

        return self.template.render(
            keyword=keyword,
            stats={
                "총 Chunk 수": f"{stats.get('chunk_count', 0):,}개",
                "Entity 등록": f"{stats.get('entity_count', 0)}개 ({entity_summary})",
                "관련 문서 수": f"{doc_count}개",
            },
            documents=docs,
            samples=unique_samples[:5],
            conclusion=conclusion,
        )

    def _generate_conclusion(
        self,
        keyword: str,
        stats: Dict[str, Any],
        docs: List[Dict[str, Any]],
        context: AgentContext
    ) -> str:
        """결론 텍스트 생성"""
        chunk_count = stats.get("chunk_count", 0)
        doc_count = len(docs)

        if chunk_count == 0:
            return f"**{keyword}**에 대한 정보를 지식 베이스에서 찾을 수 없습니다."

        # 상위 문서 카테고리 분석
        categories = {}
        for doc in docs[:5]:
            filename = doc.get("filename", "")
            if "Utility" in filename:
                categories["유틸리티 가이드"] = categories.get("유틸리티 가이드", 0) + doc.get("count", 0)
            elif "Dataset" in filename:
                categories["데이터셋 가이드"] = categories.get("데이터셋 가이드", 0) + doc.get("count", 0)
            elif "Admin" in filename:
                categories["관리자 가이드"] = categories.get("관리자 가이드", 0) + doc.get("count", 0)
            elif "Error" in filename:
                categories["에러 레퍼런스"] = categories.get("에러 레퍼런스", 0) + doc.get("count", 0)
            elif "Release" in filename:
                categories["릴리스 노트"] = categories.get("릴리스 노트", 0) + doc.get("count", 0)
            elif "Install" in filename:
                categories["설치 가이드"] = categories.get("설치 가이드", 0) + doc.get("count", 0)
            else:
                categories["기타 문서"] = categories.get("기타 문서", 0) + doc.get("count", 0)

        cat_summary = ", ".join(
            f"{k} ({v}회)" for k, v in sorted(categories.items(), key=lambda x: -x[1])
        ) if categories else "분류 없음"

        return (
            f"**{keyword}**는 OpenFrame 학습데이터에 **{chunk_count:,}개**의 청크에 걸쳐 "
            f"**{doc_count}개** 문서에 문서화되어 있습니다. "
            f"주요 문서 유형: {cat_summary}."
        )


# Factory function for creating the tool
def create_comprehensive_search_tool() -> ComprehensiveSearchTool:
    """Create a comprehensive search tool instance"""
    return ComprehensiveSearchTool()
