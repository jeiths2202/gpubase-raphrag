"""
Entity Lookup Service for Semantic Search

Entity 기반 직접 조회 서비스
- Command Index
- Error Code Index
- Product Index
- Summary 기반 조회
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from app.api.models.query_analysis import ExtractedEntity, RetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class EntityMatch:
    """Entity 매칭 결과"""
    entity_type: str
    entity_value: str
    doc_id: str
    content: str
    title: str
    source_file: str
    confidence: float = 1.0


class EntityLookupService:
    """Entity 기반 직접 조회 서비스"""

    def __init__(
        self,
        neo4j_driver=None,
        summary_base_path: str = None,
    ):
        self.neo4j = neo4j_driver
        self.summary_base_path = summary_base_path or os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "uploads", "summaries"
        )

        # Entity 인덱스 (메모리 캐시)
        self.command_index: Dict[str, List[str]] = {}    # command → chunk_ids
        self.error_index: Dict[str, List[str]] = {}      # error_code → chunk_ids
        self.product_index: Dict[str, List[str]] = {}    # product → chunk_ids

        # Summary 인덱스
        self.summary_command_index: Dict[str, str] = {}  # command → file_path
        self.summary_error_index: Dict[str, str] = {}    # error_code → file_path

        self._initialized = False

    async def initialize(self):
        """인덱스 초기화"""
        if self._initialized:
            return

        try:
            # Neo4j에서 Entity 인덱스 로드
            if self.neo4j:
                await self._load_neo4j_index()

            # Summary 파일 인덱스 로드
            self._load_summary_index()

            self._initialized = True
            logger.info("EntityLookupService initialized successfully")

        except Exception as e:
            logger.error(f"EntityLookupService initialization failed: {e}")
            self._initialized = True  # 실패해도 계속 진행

    async def _load_neo4j_index(self):
        """Neo4j에서 Entity 인덱스 로드"""
        try:
            query = """
            MATCH (e:Entity)-[:MENTIONED_IN]->(c:Chunk)
            RETURN e.type as type, e.name as name, collect(c.id) as chunk_ids
            LIMIT 10000
            """
            async with self.neo4j.session() as session:
                result = await session.run(query)
                records = await result.data()

                for record in records:
                    entity_type = record.get("type", "").lower()
                    entity_name = record.get("name", "").lower()
                    chunk_ids = record.get("chunk_ids", [])

                    if entity_type == "command":
                        self.command_index[entity_name] = chunk_ids
                    elif entity_type == "error_code":
                        self.error_index[entity_name] = chunk_ids
                    elif entity_type == "product":
                        self.product_index[entity_name] = chunk_ids

            logger.info(f"Loaded {len(self.command_index)} commands, "
                       f"{len(self.error_index)} errors, "
                       f"{len(self.product_index)} products from Neo4j")

        except Exception as e:
            logger.warning(f"Neo4j index loading failed: {e}")

    def _load_summary_index(self):
        """Summary 파일 인덱스 로드"""
        summary_path = Path(self.summary_base_path)

        # Commands 인덱스
        commands_path = summary_path / "commands"
        if commands_path.exists():
            for file in commands_path.glob("*.md"):
                # 파일명에서 명령어 추출
                content = file.read_text(encoding="utf-8")
                # ## 명령어명 패턴 찾기
                import re
                for match in re.finditer(r'^##\s+(\w+)\s*$', content, re.MULTILINE):
                    cmd = match.group(1).lower()
                    self.summary_command_index[cmd] = str(file)

        # Error codes 인덱스
        errors_path = summary_path / "error-codes"
        if errors_path.exists():
            for file in errors_path.glob("*.md"):
                content = file.read_text(encoding="utf-8")
                # 에러 코드 패턴 찾기
                import re
                for match in re.finditer(r'\|\s*(-?\d{4,5})\s*\|', content):
                    code = match.group(1)
                    if not code.startswith("-"):
                        code = f"-{code}"
                    self.summary_error_index[code] = str(file)

        logger.info(f"Loaded {len(self.summary_command_index)} commands, "
                   f"{len(self.summary_error_index)} errors from summaries")

    async def lookup(
        self,
        entities: List[ExtractedEntity],
        max_results: int = 10
    ) -> List[RetrievalResult]:
        """Entity 기반 문서 조회"""
        if not self._initialized:
            await self.initialize()

        results = []

        for entity in entities:
            entity_results = await self._lookup_single(entity, max_results)
            results.extend(entity_results)

        # 중복 제거 및 상위 결과 반환
        seen_ids = set()
        unique_results = []
        for r in results:
            if r.doc_id not in seen_ids:
                seen_ids.add(r.doc_id)
                unique_results.append(r)

        return unique_results[:max_results]

    async def _lookup_single(
        self,
        entity: ExtractedEntity,
        max_results: int
    ) -> List[RetrievalResult]:
        """단일 Entity 조회"""
        results = []
        entity_value = entity.value.lower()

        # 1. Summary 파일에서 조회
        summary_results = self._lookup_from_summary(entity)
        results.extend(summary_results)

        # 2. Neo4j 인덱스에서 조회
        if self.neo4j:
            neo4j_results = await self._lookup_from_neo4j(entity, max_results)
            results.extend(neo4j_results)

        return results[:max_results]

    def _lookup_from_summary(self, entity: ExtractedEntity) -> List[RetrievalResult]:
        """Summary 파일에서 Entity 조회"""
        results = []
        entity_value = entity.value.lower()

        if entity.type == "command":
            # 명령어 인덱스에서 조회
            if entity_value in self.summary_command_index:
                file_path = self.summary_command_index[entity_value]
                content = self._extract_command_section(file_path, entity.value)
                if content:
                    results.append(RetrievalResult(
                        doc_id=f"summary_cmd_{entity_value}",
                        content=content,
                        source="entity",
                        score=1.0,
                        metadata={
                            "entity_type": "command",
                            "entity_value": entity.value,
                            "source_type": "summary"
                        },
                        document_title=f"Command: {entity.value}"
                    ))

        elif entity.type == "error_code":
            # 에러 코드 인덱스에서 조회
            error_code = entity.value if entity.value.startswith("-") else f"-{entity.value}"
            if error_code in self.summary_error_index:
                file_path = self.summary_error_index[error_code]
                content = self._extract_error_section(file_path, error_code)
                if content:
                    results.append(RetrievalResult(
                        doc_id=f"summary_err_{error_code}",
                        content=content,
                        source="entity",
                        score=1.0,
                        metadata={
                            "entity_type": "error_code",
                            "entity_value": error_code,
                            "source_type": "summary"
                        },
                        document_title=f"Error: {error_code}"
                    ))

        return results

    def _extract_command_section(self, file_path: str, command: str) -> Optional[str]:
        """명령어 섹션 추출"""
        try:
            content = Path(file_path).read_text(encoding="utf-8")
            import re

            # ## 명령어 ~ 다음 ## 또는 파일 끝까지
            pattern = rf'^##\s+{re.escape(command)}\s*\n([\s\S]*?)(?=^##\s|\Z)'
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

            if match:
                return f"## {command}\n{match.group(1).strip()}"

            return None

        except Exception as e:
            logger.warning(f"Failed to extract command section: {e}")
            return None

    def _extract_error_section(self, file_path: str, error_code: str) -> Optional[str]:
        """에러 코드 섹션 추출"""
        try:
            content = Path(file_path).read_text(encoding="utf-8")

            # 테이블에서 해당 에러 코드 행 찾기
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if error_code in line and "|" in line:
                    # 해당 행과 전후 컨텍스트 반환
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    return "\n".join(lines[start:end])

            return None

        except Exception as e:
            logger.warning(f"Failed to extract error section: {e}")
            return None

    async def _lookup_from_neo4j(
        self,
        entity: ExtractedEntity,
        max_results: int
    ) -> List[RetrievalResult]:
        """Neo4j에서 Entity 조회"""
        results = []
        entity_value = entity.value.lower()

        try:
            # 인덱스에서 chunk ID 조회
            chunk_ids = []
            if entity.type == "command" and entity_value in self.command_index:
                chunk_ids = self.command_index[entity_value]
            elif entity.type == "error_code" and entity_value in self.error_index:
                chunk_ids = self.error_index[entity_value]
            elif entity.type == "product" and entity_value in self.product_index:
                chunk_ids = self.product_index[entity_value]

            if not chunk_ids:
                return results

            # Chunk 내용 조회
            query = """
            MATCH (c:Chunk)
            WHERE c.id IN $chunk_ids
            OPTIONAL MATCH (c)-[:PART_OF]->(d:Document)
            RETURN c.id as id, c.content as content,
                   d.title as title, d.pdf_path as pdf_path
            LIMIT $limit
            """
            async with self.neo4j.session() as session:
                result = await session.run(
                    query,
                    chunk_ids=chunk_ids[:max_results],
                    limit=max_results
                )
                records = await result.data()

                for record in records:
                    results.append(RetrievalResult(
                        doc_id=record["id"],
                        content=record.get("content", ""),
                        source="entity",
                        score=0.95,  # Entity 매칭은 높은 점수
                        metadata={
                            "entity_type": entity.type,
                            "entity_value": entity.value,
                            "source_type": "neo4j"
                        },
                        document_title=record.get("title"),
                        pdf_path=record.get("pdf_path")
                    ))

        except Exception as e:
            logger.warning(f"Neo4j entity lookup failed: {e}")

        return results


# 싱글톤 인스턴스
_service_instance: Optional[EntityLookupService] = None


def get_entity_lookup_service(neo4j_driver=None) -> EntityLookupService:
    """EntityLookupService 싱글톤 반환"""
    global _service_instance
    if _service_instance is None:
        _service_instance = EntityLookupService(neo4j_driver=neo4j_driver)
    return _service_instance
