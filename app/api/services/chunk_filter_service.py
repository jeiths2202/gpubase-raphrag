"""검색 결과 청크 필터링 서비스

Context Pollution 방지를 위해 질문과 관련 없는 청크를 필터링합니다.

RAG Context Pollution Fix - Phase 2
- osctdlrm 질문에 oscsiggen이 포함되는 등의 문제 해결
- 질문에서 추출한 명령어 Entity 기반으로 청크 필터링
"""

import re
import os
import logging
from typing import List, Dict, Optional, Set

logger = logging.getLogger(__name__)

# Feature Toggle
ENABLE_CHUNK_FILTER = os.getenv("ENABLE_CHUNK_FILTER", "true").lower() == "true"
CHUNK_FILTER_MIN_RESULTS = int(os.getenv("CHUNK_FILTER_MIN_RESULTS", "2"))


class ChunkFilterService:
    """검색 결과 청크 필터링

    질문에서 추출한 명령어/Entity 기반으로 관련 없는 청크를 필터링합니다.
    Context Pollution (osctdlrm 질문에 oscsiggen 포함 등) 방지.
    """

    # OpenFrame 명령어 패턴 (osc*, tjes*, tacf*, hidb*, ndb* 등)
    COMMAND_PATTERNS = [
        r'\b(osc[a-z]{2,})\b',    # osctdlrm, oscsiggen, oscboot, oscdown, oscmgr
        r'\b(tjes[a-z]*)\b',      # tjesmgr, tjes
        r'\b(tacf[a-z]*)\b',      # tacfmgr, tacf
        r'\b(hidb[a-z]*)\b',      # hidbmgr, hidb
        r'\b(ndb[a-z]*)\b',       # ndbmgr, ndb
        r'\b(osi[a-z]*)\b',       # osimgr, osi
        r'\b(vol[a-z]*mgr)\b',    # volmgr
        r'\b(cat[a-z]*mgr)\b',    # catmgr
        r'\b(tmboot|tmdown|ofboot|ofdown)\b',  # 시스템 명령어
        r'\b(idcams|iebgener|iebcopy|dfsort)\b',  # 유틸리티
        r'\b(dsmigin|dsmigout)\b',  # 데이터셋 마이그레이션
    ]

    # 필터링 제외 패턴 (일반적인 질문)
    SKIP_FILTER_PATTERNS = [
        r'(コマンド|명령어|command)(一覧|목록|list)',  # 명령어 목록 질문
        r'(比較|비교|compare|vs\.?)',  # 비교 질문
        r'(全て|모든|all|every)',  # 전체 관련 질문
        r'(関連|관련|related)',  # 관련 명령어 질문
    ]

    def __init__(self):
        self._command_pattern = re.compile(
            '|'.join(self.COMMAND_PATTERNS),
            re.IGNORECASE
        )
        self._skip_pattern = re.compile(
            '|'.join(self.SKIP_FILTER_PATTERNS),
            re.IGNORECASE
        )

    def filter_by_query_entity(
        self,
        query: str,
        chunks: List[Dict],
        min_chunks: int = CHUNK_FILTER_MIN_RESULTS
    ) -> List[Dict]:
        """질문의 주요 Entity 기반 청크 필터링

        Args:
            query: 사용자 질문
            chunks: 검색된 청크 목록 (각 청크는 'content' 키 필요)
            min_chunks: 최소 반환 청크 수 (폴백)

        Returns:
            필터링된 청크 목록

        Example:
            >>> service = ChunkFilterService()
            >>> chunks = [
            ...     {'content': 'osctdlrm is a management tool...'},
            ...     {'content': 'oscsiggen generates sign files...'},
            ...     {'content': 'osctdlrm syntax: osctdlrm [options]...'},
            ... ]
            >>> filtered = service.filter_by_query_entity(
            ...     'osctdlrmについて説明してください', chunks
            ... )
            >>> len(filtered)
            2
        """
        if not ENABLE_CHUNK_FILTER:
            logger.debug("[ChunkFilter] Feature disabled, skipping filter")
            return chunks

        if not chunks:
            return chunks

        # 1. 필터링 스킵 조건 확인
        if self._should_skip_filter(query):
            logger.debug("[ChunkFilter] Skip pattern detected, returning all chunks")
            return chunks

        # 2. 질문에서 명령어 Entity 추출
        query_command = self._extract_command_entity(query)

        if not query_command:
            logger.debug("[ChunkFilter] No command entity in query, skipping filter")
            return chunks

        logger.info(f"[ChunkFilter] Query command entity: '{query_command}'")

        # 3. 질문 명령어가 포함된 청크만 필터링
        filtered = []
        filtered_out = []

        for chunk in chunks:
            content = chunk.get('content', '') or chunk.get('text', '')
            if not content:
                filtered.append(chunk)  # 내용 없으면 유지
                continue

            if self._chunk_contains_entity(content, query_command):
                filtered.append(chunk)
            else:
                # 다른 명령어가 있는지 확인 (로깅용)
                other_commands = self._extract_all_commands(content)
                other_commands.discard(query_command.lower())
                if other_commands:
                    filtered_out.append({
                        'chunk_preview': content[:100],
                        'other_commands': list(other_commands)
                    })

        # 4. 필터링 결과 로깅
        if filtered_out:
            logger.info(
                f"[ChunkFilter] Filtered out {len(filtered_out)} chunks with other commands: "
                f"{[f['other_commands'] for f in filtered_out[:3]]}"
            )

        # 5. 폴백: 필터링 후 너무 적으면 원본 상위 결과 유지
        if len(filtered) < min_chunks:
            logger.warning(
                f"[ChunkFilter] Only {len(filtered)} chunks after filter, "
                f"keeping top {min_chunks} original chunks as fallback"
            )
            return chunks[:min_chunks]

        logger.info(f"[ChunkFilter] Filtered {len(chunks)} → {len(filtered)} chunks")
        return filtered

    def _should_skip_filter(self, query: str) -> bool:
        """필터링 스킵 조건 확인

        명령어 목록 질문, 비교 질문 등은 필터링하지 않음.

        Args:
            query: 사용자 질문

        Returns:
            스킵 여부
        """
        return bool(self._skip_pattern.search(query))

    def _extract_command_entity(self, query: str) -> Optional[str]:
        """질문에서 명령어 Entity 추출

        Args:
            query: 사용자 질문

        Returns:
            추출된 명령어 또는 None
        """
        matches = self._command_pattern.findall(query)
        if matches:
            # 첫 번째로 매칭된 명령어 반환
            # findall은 그룹이 있으면 튜플로 반환할 수 있음
            match = matches[0]
            if isinstance(match, tuple):
                # 비어있지 않은 첫 번째 그룹 반환
                return next((m for m in match if m), None)
            return match
        return None

    def _extract_all_commands(self, text: str) -> Set[str]:
        """텍스트에서 모든 명령어 추출

        Args:
            text: 텍스트

        Returns:
            추출된 명령어 집합 (소문자)
        """
        matches = self._command_pattern.findall(text)
        commands = set()
        for match in matches:
            if isinstance(match, tuple):
                for m in match:
                    if m:
                        commands.add(m.lower())
            elif match:
                commands.add(match.lower())
        return commands

    def _chunk_contains_entity(self, content: str, entity: str) -> bool:
        """청크에 Entity가 포함되어 있는지 확인

        Args:
            content: 청크 내용
            entity: 확인할 Entity

        Returns:
            포함 여부
        """
        # 단어 경계를 고려한 대소문자 무시 매칭
        pattern = rf'\b{re.escape(entity)}\b'
        return bool(re.search(pattern, content, re.IGNORECASE))


# 싱글톤 인스턴스
_chunk_filter_service: Optional[ChunkFilterService] = None


def get_chunk_filter_service() -> ChunkFilterService:
    """ChunkFilterService 싱글톤 반환"""
    global _chunk_filter_service
    if _chunk_filter_service is None:
        _chunk_filter_service = ChunkFilterService()
    return _chunk_filter_service
