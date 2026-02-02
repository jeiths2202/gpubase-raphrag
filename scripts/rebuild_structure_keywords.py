#!/usr/bin/env python3
"""
STRUCTURES 인덱스 키워드 재생성 스크립트

기존 _structure.json 파일들의 키워드를 CJK 토크나이저로 재추출하고
index.json을 업데이트합니다.

Usage:
    python scripts/rebuild_structure_keywords.py [summaries_dir]

    # 기본 경로 사용
    python scripts/rebuild_structure_keywords.py

    # 커스텀 경로
    python scripts/rebuild_structure_keywords.py /opt/kms/uploads/summaries
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def rebuild_keywords(summaries_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    STRUCTURES 디렉토리의 모든 문서 키워드 재생성

    Args:
        summaries_dir: summaries 디렉토리 경로

    Returns:
        처리 결과 통계
    """
    # Import here to allow script to show usage even without dependencies
    try:
        from app.api.services.cjk_tokenizer_service import get_cjk_tokenizer_service
    except ImportError as e:
        logger.error(f"Failed to import CJKTokenizerService: {e}")
        logger.error("Please ensure you're running from the project root directory")
        return {"error": "Import failed"}

    # Determine summaries directory
    if summaries_dir is None:
        # Try multiple paths
        possible_paths = [
            project_root / "uploads" / "summaries",
            Path("/opt/kms/uploads/summaries"),
        ]
        for path in possible_paths:
            if path.exists():
                summaries_dir = path
                break

    if summaries_dir is None or not summaries_dir.exists():
        logger.error(f"summaries 디렉토리를 찾을 수 없습니다")
        return {"error": "Directory not found"}

    structures_dir = summaries_dir / "structures"
    if not structures_dir.exists():
        logger.error(f"structures 디렉토리가 없습니다: {structures_dir}")
        return {"error": "structures directory not found"}

    logger.info(f"Processing structures from: {structures_dir}")

    tokenizer = get_cjk_tokenizer_service()

    stats = {
        "processed": 0,
        "updated": 0,
        "errors": 0,
        "total_keywords_before": 0,
        "total_keywords_after": 0,
        "sample_changes": [],
    }

    # 1. 모든 _structure.json 파일 처리
    json_files = list(structures_dir.glob("*_structure.json"))
    logger.info(f"처리할 파일 수: {len(json_files)}")

    documents = []
    all_keywords = set()

    for json_file in json_files:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            stats["processed"] += 1

            # 기존 키워드 수집
            old_keywords = _collect_keywords_recursive(data.get("hierarchy", []))
            stats["total_keywords_before"] += len(old_keywords)

            # 새 키워드 추출
            new_keywords = set()
            _update_keywords_recursive(
                nodes=data.get("hierarchy", []),
                tokenizer=tokenizer,
                new_keywords=new_keywords
            )

            stats["total_keywords_after"] += len(new_keywords)

            # 변경사항이 있으면 저장
            if new_keywords != old_keywords:
                stats["updated"] += 1

                # 변경 샘플 기록 (처음 5개만)
                if len(stats["sample_changes"]) < 5:
                    added = new_keywords - old_keywords
                    removed = old_keywords - new_keywords
                    stats["sample_changes"].append({
                        "file": json_file.name,
                        "added": list(added)[:5],
                        "removed": list(removed)[:5],
                    })

                json_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                logger.info(f"  Updated: {json_file.name} ({len(old_keywords)} -> {len(new_keywords)} keywords)")

            # index.json용 데이터 수집
            doc_info = {
                "file_name": data.get("file_name", json_file.stem.replace("_structure", ".pdf")),
                "title": data.get("title", ""),
                "pages": data.get("total_pages", 0),
                "nodes": _count_nodes(data.get("hierarchy", [])),
                "images": len(data.get("images_index", [])),
                "valid": data.get("validation", {}).get("valid", True),
                "coverage": data.get("validation", {}).get("coverage_ratio", 1.0),
                "keywords": sorted(list(new_keywords))[:10],
            }
            documents.append(doc_info)
            all_keywords.update(new_keywords)

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"  Error processing {json_file.name}: {e}")

    # 2. index.json 업데이트
    index_path = structures_dir / "index.json"

    # 백업 기존 index.json
    if index_path.exists():
        backup_path = structures_dir / f"index_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup_path.write_text(index_path.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info(f"Backed up index.json to {backup_path.name}")

    index_data = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_documents": len(documents),
            "total_pages": sum(d["pages"] for d in documents),
            "total_nodes": sum(d["nodes"] for d in documents),
            "total_images": sum(d["images"] for d in documents),
            "valid_documents": len([d for d in documents if d["valid"]]),
        },
        "documents": documents,
        "all_keywords": sorted(list(all_keywords))[:100],
    }

    index_path.write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 3. 결과 출력
    logger.info(f"\n{'='*50}")
    logger.info(f"처리 완료")
    logger.info(f"{'='*50}")
    logger.info(f"  처리 파일: {stats['processed']}")
    logger.info(f"  업데이트: {stats['updated']}")
    logger.info(f"  에러: {stats['errors']}")
    logger.info(f"  키워드 (전): {stats['total_keywords_before']}")
    logger.info(f"  키워드 (후): {stats['total_keywords_after']}")
    logger.info(f"  전체 고유 키워드: {len(all_keywords)}")

    # CJK 키워드 통계
    cjk_keywords = [kw for kw in all_keywords if _is_cjk(kw)]
    logger.info(f"  CJK 키워드: {len(cjk_keywords)}")
    if cjk_keywords:
        logger.info(f"  샘플 CJK 키워드: {cjk_keywords[:10]}")

    # 변경 샘플 출력
    if stats["sample_changes"]:
        logger.info(f"\n변경 샘플:")
        for change in stats["sample_changes"]:
            logger.info(f"  {change['file']}:")
            if change['added']:
                logger.info(f"    + Added: {change['added']}")
            if change['removed']:
                logger.info(f"    - Removed: {change['removed']}")

    return stats


def _collect_keywords_recursive(nodes: List[Dict]) -> set:
    """노드에서 기존 키워드 수집 (재귀)"""
    keywords = set()
    for node in nodes:
        keywords.update(node.get("keywords", []))
        keywords.update(_collect_keywords_recursive(node.get("children", [])))
    return keywords


def _update_keywords_recursive(
    nodes: List[Dict],
    tokenizer,
    new_keywords: set
) -> None:
    """노드의 키워드 업데이트 (재귀)"""
    for node in nodes:
        # raw_text 또는 summary에서 키워드 추출
        text = node.get("raw_text", "") or node.get("summary", "")
        title = node.get("title", "")

        if text or title:
            extracted = tokenizer.extract_all_keywords(text, title)
            node["keywords"] = extracted[:7]
            new_keywords.update(extracted)

        # 자식 노드 처리
        _update_keywords_recursive(
            node.get("children", []),
            tokenizer,
            new_keywords
        )


def _count_nodes(nodes: List[Dict]) -> int:
    """노드 수 계산 (재귀)"""
    count = len(nodes)
    for node in nodes:
        count += _count_nodes(node.get("children", []))
    return count


def _is_cjk(text: str) -> bool:
    """CJK 문자 포함 여부 확인"""
    import re
    return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]', text))


def verify_results(summaries_dir: Optional[Path] = None) -> None:
    """
    재생성 결과 검증

    OSI 문서에 일본어 키워드가 포함되었는지 확인
    """
    if summaries_dir is None:
        summaries_dir = project_root / "uploads" / "summaries"

    index_path = summaries_dir / "structures" / "index.json"
    if not index_path.exists():
        logger.error(f"index.json not found: {index_path}")
        return

    index_data = json.loads(index_path.read_text(encoding="utf-8"))

    logger.info("\n검증: OSI 문서 키워드 확인")
    logger.info("=" * 50)

    osi_docs = [d for d in index_data["documents"] if "OSI" in d.get("file_name", "").upper()]

    for doc in osi_docs:
        keywords = doc.get("keywords", [])
        cjk_keywords = [kw for kw in keywords if _is_cjk(kw)]

        logger.info(f"\n{doc['file_name']}:")
        logger.info(f"  전체 키워드: {keywords}")
        logger.info(f"  CJK 키워드: {cjk_keywords}")

        if cjk_keywords:
            logger.info(f"  ✅ CJK 키워드 포함")
        else:
            logger.info(f"  ❌ CJK 키워드 없음 (문제!)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="STRUCTURES 인덱스 키워드 재생성")
    parser.add_argument(
        "summaries_dir",
        nargs="?",
        help="summaries 디렉토리 경로 (기본: uploads/summaries)"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="결과 검증만 수행"
    )

    args = parser.parse_args()

    summaries_path = Path(args.summaries_dir) if args.summaries_dir else None

    if args.verify:
        verify_results(summaries_path)
    else:
        stats = rebuild_keywords(summaries_path)

        if "error" not in stats:
            logger.info("\n인덱스 재생성 완료. 검증을 실행합니다...")
            verify_results(summaries_path)
