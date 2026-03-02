"""
청킹 설정

Semantic Chunker의 동작을 제어하는 설정 클래스입니다.
"""

import os
from dataclasses import dataclass


@dataclass
class ChunkingConfig:
    """청킹 설정

    환경 변수로 오버라이드 가능:
    - CHUNK_MIN_SIZE: 최소 청크 크기
    - CHUNK_TARGET_SIZE: 목표 청크 크기
    - CHUNK_MAX_SIZE: 최대 청크 크기
    - CHUNK_OVERLAP: 청크 오버랩
    """

    # 크기 제한
    min_chunk_size: int = 200       # 최소 청크 크기
    target_chunk_size: int = 800    # 목표 청크 크기
    max_chunk_size: int = 1500      # 최대 청크 크기

    # 테이블 설정
    table_size_limit: int = 3000    # 테이블 최대 크기 (초과 시 분할)
    preserve_table_integrity: bool = True  # 테이블 구조 유지
    max_table_rows_per_chunk: int = 50     # 청크당 최대 테이블 행 수

    # 이미지 설정
    process_images: bool = True     # 이미지 처리 여부
    image_cache_enabled: bool = True # 이미지 캐싱
    vision_llm_timeout: int = 60    # Vision LLM 타임아웃 (초)
    max_concurrent_image_calls: int = 3  # 동시 Vision LLM 호출 수

    # 섹션 설정
    respect_section_boundaries: bool = True  # 섹션 경계 존중
    include_section_context: bool = True     # 섹션 제목 포함
    min_section_level: int = 1      # 최소 섹션 레벨 (1=Chapter)
    max_section_level: int = 4      # 최대 섹션 레벨 (4=Paragraph)

    # 오버랩 설정
    chunk_overlap: int = 100        # 청크 오버랩
    use_adaptive_overlap: bool = True  # 적응형 오버랩

    # 단락 재구성 설정
    sentence_enders: str = ".!?。？！"  # 문장 종결자
    short_line_threshold: int = 40      # 짧은 줄 기준 (병합 대상)

    def __post_init__(self):
        """환경 변수에서 설정 로드"""
        self.min_chunk_size = int(os.getenv("CHUNK_MIN_SIZE", self.min_chunk_size))
        self.target_chunk_size = int(os.getenv("CHUNK_TARGET_SIZE", self.target_chunk_size))
        self.max_chunk_size = int(os.getenv("CHUNK_MAX_SIZE", self.max_chunk_size))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", self.chunk_overlap))
        self.vision_llm_timeout = int(os.getenv("VISION_LLM_TIMEOUT", self.vision_llm_timeout))

    def validate(self) -> bool:
        """설정 유효성 검사"""
        if self.min_chunk_size >= self.target_chunk_size:
            raise ValueError("min_chunk_size must be less than target_chunk_size")
        if self.target_chunk_size >= self.max_chunk_size:
            raise ValueError("target_chunk_size must be less than max_chunk_size")
        if self.chunk_overlap >= self.min_chunk_size:
            raise ValueError("chunk_overlap must be less than min_chunk_size")
        return True

    def get_adaptive_overlap(self, chunk_size: int) -> int:
        """청크 크기에 따른 적응형 오버랩 계산

        작은 청크: 오버랩 비율 높임 (최대 20%)
        큰 청크: 오버랩 비율 낮춤 (최소 5%)
        """
        if not self.use_adaptive_overlap:
            return self.chunk_overlap

        ratio = min(0.2, max(0.05, 100 / chunk_size))
        return int(chunk_size * ratio)
