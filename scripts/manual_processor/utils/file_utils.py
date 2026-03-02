"""파일 유틸리티"""

import logging
from pathlib import Path
from typing import List, Optional, Generator

from ..config import config

logger = logging.getLogger(__name__)


def find_manuals(
    base_dir: Optional[Path] = None,
    pattern: str = "**/*.pdf"
) -> Generator[Path, None, None]:
    """매뉴얼 PDF 파일 검색

    Args:
        base_dir: 검색 기준 디렉토리 (기본: config.manuals_dir)
        pattern: glob 패턴

    Yields:
        PDF 파일 경로
    """
    base_dir = base_dir or config.manuals_dir

    if not base_dir.exists():
        logger.error(f"디렉토리가 존재하지 않습니다: {base_dir}")
        return

    for pdf_path in base_dir.glob(pattern):
        if pdf_path.is_file():
            yield pdf_path


def find_error_guides(base_dir: Optional[Path] = None) -> Generator[Path, None, None]:
    """에러 참조 가이드만 검색"""
    for pdf_path in find_manuals(base_dir):
        if "Error" in pdf_path.name and "Reference" in pdf_path.name:
            yield pdf_path


def find_guide_by_type(
    guide_type: str,
    base_dir: Optional[Path] = None
) -> Generator[Path, None, None]:
    """특정 가이드 타입 검색

    Args:
        guide_type: 가이드 타입 (예: "TJES-Guide", "Installation-Guide")
        base_dir: 검색 기준 디렉토리
    """
    for pdf_path in find_manuals(base_dir):
        if guide_type in pdf_path.name:
            yield pdf_path


def ensure_dir(dir_path: Path) -> Path:
    """디렉토리 생성 보장"""
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def get_relative_path(file_path: Path, base_dir: Optional[Path] = None) -> str:
    """상대 경로 반환"""
    base_dir = base_dir or config.summaries_dir
    try:
        return str(file_path.relative_to(base_dir))
    except ValueError:
        return str(file_path)


def group_manuals_by_product(
    base_dir: Optional[Path] = None
) -> dict[str, List[Path]]:
    """제품별로 매뉴얼 그룹화"""
    from collections import defaultdict

    groups = defaultdict(list)

    for pdf_path in find_manuals(base_dir):
        filename = pdf_path.name

        # 파일명에서 제품 추출
        product = None
        for prod_key in config.products.keys():
            if prod_key in filename:
                product = prod_key
                break

        if product:
            groups[product].append(pdf_path)
        else:
            groups["other"].append(pdf_path)

    return dict(groups)


def get_manual_language(pdf_path: Path) -> str:
    """매뉴얼 언어 감지"""
    filename = pdf_path.name.lower()

    if "_ja." in filename or "_ja_" in filename:
        return "ja"
    elif "_jp." in filename or "_jp_" in filename:
        return "ja"  # jp도 일본어
    elif "_en." in filename or "_en_" in filename:
        return "en"
    elif "_ko." in filename or "_ko_" in filename:
        return "ko"

    # 디렉토리 이름에서 추측
    parent_name = pdf_path.parent.name.lower()
    if "jp" in parent_name or "japanese" in parent_name:
        return "ja"
    elif "en" in parent_name or "english" in parent_name:
        return "en"

    return "ja"  # 기본값
