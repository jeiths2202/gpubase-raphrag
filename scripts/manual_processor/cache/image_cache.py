"""
Image Cache

Vision LLM 결과를 캐싱하여 중복 API 호출을 방지합니다.
파일 기반 캐시로 세션 간에도 캐시가 유지됩니다.
"""

import os
import json
import logging
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ImageCache:
    """Vision LLM 결과 캐시

    이미지 해시를 키로 사용하여 Vision LLM 결과를 캐싱합니다.
    파일 기반 캐시로 프로세스 재시작 후에도 캐시가 유지됩니다.

    캐시 구조:
    cache_dir/
    ├── index.json          # 해시 → 메타데이터 매핑
    └── descriptions/       # 설명 텍스트 파일
        ├── {hash}.json     # 개별 캐시 엔트리
        └── ...
    """

    DEFAULT_CACHE_DIR = "uploads/image_cache"
    INDEX_FILE = "index.json"
    DESCRIPTIONS_DIR = "descriptions"

    # 캐시 만료 기간 (일)
    CACHE_EXPIRY_DAYS = 30

    def __init__(self, cache_dir: str = None):
        """
        Args:
            cache_dir: 캐시 디렉토리 경로 (기본값: uploads/image_cache)
        """
        self.cache_dir = Path(cache_dir or self.DEFAULT_CACHE_DIR)
        self.descriptions_dir = self.cache_dir / self.DESCRIPTIONS_DIR
        self.index_path = self.cache_dir / self.INDEX_FILE

        self._ensure_cache_dirs()
        self._index: Dict[str, Dict[str, Any]] = self._load_index()

    def _ensure_cache_dirs(self) -> None:
        """캐시 디렉토리 생성"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.descriptions_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        """인덱스 파일 로드"""
        if self.index_path.exists():
            try:
                with open(self.index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"캐시 인덱스 로드 실패: {e}")
                return {}
        return {}

    def _save_index(self) -> None:
        """인덱스 파일 저장"""
        try:
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"캐시 인덱스 저장 실패: {e}")

    @staticmethod
    def compute_hash(image_data: bytes) -> str:
        """이미지 데이터의 MD5 해시 계산

        Args:
            image_data: 이미지 바이너리 데이터

        Returns:
            MD5 해시 문자열
        """
        return hashlib.md5(image_data).hexdigest()

    def get(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """캐시에서 이미지 설명 조회

        Args:
            image_hash: 이미지 MD5 해시

        Returns:
            캐시 엔트리 (description, image_type, created_at 등) 또는 None
        """
        if image_hash not in self._index:
            return None

        # 만료 확인
        entry = self._index[image_hash]
        created_at = datetime.fromisoformat(entry.get("created_at", "2000-01-01"))
        if datetime.now() - created_at > timedelta(days=self.CACHE_EXPIRY_DAYS):
            logger.debug(f"캐시 만료: {image_hash}")
            self._remove_entry(image_hash)
            return None

        # 설명 파일 읽기
        desc_path = self.descriptions_dir / f"{image_hash}.json"
        if not desc_path.exists():
            logger.warning(f"캐시 설명 파일 없음: {image_hash}")
            self._remove_entry(image_hash)
            return None

        try:
            with open(desc_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"캐시 설명 파일 읽기 실패: {e}")
            self._remove_entry(image_hash)
            return None

    def set(
        self,
        image_hash: str,
        description: str,
        image_type: str = "other",
        metadata: Dict[str, Any] = None
    ) -> None:
        """캐시에 이미지 설명 저장

        Args:
            image_hash: 이미지 MD5 해시
            description: Vision LLM이 생성한 설명
            image_type: 이미지 유형 (diagram, flowchart, screenshot 등)
            metadata: 추가 메타데이터
        """
        now = datetime.now().isoformat()

        entry = {
            "description": description,
            "image_type": image_type,
            "created_at": now,
            "metadata": metadata or {}
        }

        # 설명 파일 저장
        desc_path = self.descriptions_dir / f"{image_hash}.json"
        try:
            with open(desc_path, 'w', encoding='utf-8') as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"캐시 설명 파일 저장 실패: {e}")
            return

        # 인덱스 업데이트
        self._index[image_hash] = {
            "created_at": now,
            "image_type": image_type,
            "size": len(description)
        }
        self._save_index()

        logger.debug(f"캐시 저장: {image_hash} ({image_type})")

    def _remove_entry(self, image_hash: str) -> None:
        """캐시 엔트리 제거"""
        # 설명 파일 삭제
        desc_path = self.descriptions_dir / f"{image_hash}.json"
        if desc_path.exists():
            try:
                desc_path.unlink()
            except IOError:
                pass

        # 인덱스에서 제거
        if image_hash in self._index:
            del self._index[image_hash]
            self._save_index()

    def clear_expired(self) -> int:
        """만료된 캐시 엔트리 정리

        Returns:
            삭제된 엔트리 수
        """
        expired = []
        now = datetime.now()

        for image_hash, entry in self._index.items():
            created_at = datetime.fromisoformat(entry.get("created_at", "2000-01-01"))
            if now - created_at > timedelta(days=self.CACHE_EXPIRY_DAYS):
                expired.append(image_hash)

        for image_hash in expired:
            self._remove_entry(image_hash)

        if expired:
            logger.info(f"만료된 캐시 {len(expired)}개 정리")

        return len(expired)

    def clear_all(self) -> int:
        """모든 캐시 삭제

        Returns:
            삭제된 엔트리 수
        """
        count = len(self._index)

        # 모든 설명 파일 삭제
        for desc_file in self.descriptions_dir.glob("*.json"):
            try:
                desc_file.unlink()
            except IOError:
                pass

        # 인덱스 초기화
        self._index = {}
        self._save_index()

        logger.info(f"캐시 전체 삭제: {count}개")
        return count

    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계 조회

        Returns:
            통계 정보 (total_entries, total_size, type_counts 등)
        """
        type_counts = {}
        total_size = 0

        for entry in self._index.values():
            img_type = entry.get("image_type", "other")
            type_counts[img_type] = type_counts.get(img_type, 0) + 1
            total_size += entry.get("size", 0)

        return {
            "total_entries": len(self._index),
            "total_size_chars": total_size,
            "type_counts": type_counts,
            "cache_dir": str(self.cache_dir)
        }

    def has(self, image_hash: str) -> bool:
        """캐시 존재 여부 확인 (만료 확인 포함)

        Args:
            image_hash: 이미지 MD5 해시

        Returns:
            캐시 존재 여부
        """
        return self.get(image_hash) is not None
