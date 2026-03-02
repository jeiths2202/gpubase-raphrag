"""
Phase 1: CSV → Meta Index
SearchIssue_template.csv 파싱 → uploads/ims_issues/index.json
"""

import csv
import json
import logging
from io import StringIO
from pathlib import Path
from typing import Optional

from .config import (
    CSV_COLUMNS,
    DEFAULT_CSV,
    IMS_PRODUCT_TO_PRODUCT_ID,
    OUTPUT_DIR,
)

logger = logging.getLogger(__name__)


def parse_csv(csv_path: Path) -> list[dict]:
    """
    CSV 파싱 → 이슈 메타데이터 리스트.

    CSV는 헤더 없이 데이터 행만 포함하거나,
    상단에 필터/메타 행이 있을 수 있음. 숫자 ID로 시작하는 행만 파싱.
    """
    issues: list[dict] = []

    text = csv_path.read_text(encoding="utf-8-sig")
    reader = csv.reader(StringIO(text))

    for row_num, row in enumerate(reader, start=1):
        if not row or not row[0].strip():
            continue

        # ID가 숫자인 행만 데이터로 취급 (헤더/필터 행 건너뛰기)
        ims_id = row[0].strip()
        if not ims_id.isdigit():
            logger.debug(f"Line {row_num}: skipping non-data row (id={ims_id!r})")
            continue

        # 컬럼 수 부족하면 빈 문자열로 패딩
        padded = row + [""] * max(0, len(CSV_COLUMNS) - len(row))

        meta = {}
        for i, col_name in enumerate(CSV_COLUMNS):
            if col_name.startswith("col_"):
                continue  # 불필요한 컬럼 건너뛰기
            meta[col_name] = padded[i].strip()

        # product_id 매핑
        meta["product_id"] = IMS_PRODUCT_TO_PRODUCT_ID.get(
            meta.get("product", ""), ""
        )

        # 링크 필드 → IMS URL
        meta["source_url"] = (
            f"https://ims.tmaxsoft.com/tody/ims/issue/issueView.do?issueId={ims_id}"
        )

        # 불필요 필드 제거
        meta.pop("link", None)

        issues.append(meta)

    logger.info(f"Parsed {len(issues)} issues from {csv_path.name}")
    return issues


def save_index(
    issues: list[dict],
    output_dir: Optional[Path] = None,
) -> Path:
    """
    index.json 저장. 기존 인덱스와 병합, 중복(ims_id) 제거.
    새 레코드가 기존 레코드를 덮어씀.
    """
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "index.json"

    # 기존 인덱스 로드
    existing: dict[str, dict] = {}
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            for item in data:
                existing[item["ims_id"]] = item
            logger.info(f"Loaded {len(existing)} existing entries from index.json")
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load existing index: {e}")

    # 병합 (새 데이터가 기존 데이터를 덮어씀)
    new_count = 0
    updated_count = 0
    for issue in issues:
        ims_id = issue["ims_id"]
        if ims_id in existing:
            updated_count += 1
        else:
            new_count += 1
        existing[ims_id] = issue

    # 정렬 (최신 ID 먼저)
    merged = sorted(existing.values(), key=lambda x: int(x["ims_id"]), reverse=True)

    index_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info(
        f"Saved index.json: {len(merged)} total "
        f"(+{new_count} new, ~{updated_count} updated)"
    )
    return index_path


def run(csv_path: Optional[str] = None, output_dir: Optional[str] = None) -> Path:
    """CLI 진입점: CSV 파싱 → index.json 저장."""
    csv_p = Path(csv_path) if csv_path else DEFAULT_CSV
    out_p = Path(output_dir) if output_dir else OUTPUT_DIR

    if not csv_p.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_p}")

    issues = parse_csv(csv_p)
    if not issues:
        raise ValueError("No issues parsed from CSV")

    return save_index(issues, out_p)
