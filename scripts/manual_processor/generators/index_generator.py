"""인덱스 생성 모듈"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict

from ..config import config

logger = logging.getLogger(__name__)


class IndexGenerator:
    """전체 인덱스 생성기

    요약본 디렉토리의 모든 파일을 스캔하여 통합 인덱스를 생성합니다.
    AI Agent가 빠르게 검색할 수 있도록 최적화됩니다.
    """

    def __init__(self, summaries_dir: Optional[Path] = None):
        self.summaries_dir = summaries_dir or config.summaries_dir

    def generate_master_index(self) -> Path:
        """마스터 인덱스 생성"""
        index_data = {
            "generated": datetime.now().isoformat(),
            "version": "1.0",
            "directories": {},
            "search_index": {},
            "statistics": {}
        }

        # 각 디렉토리 스캔
        for subdir in ["error-codes", "glossary", "products", "components", "commands"]:
            dir_path = self.summaries_dir / subdir
            if dir_path.exists():
                index_data["directories"][subdir] = self._scan_directory(dir_path)

        # 검색 인덱스 생성
        index_data["search_index"] = self._build_search_index(index_data["directories"])

        # 통계
        index_data["statistics"] = self._calculate_statistics(index_data)

        # 마크다운 인덱스 생성
        md_path = self._generate_markdown_index(index_data)

        # JSON 인덱스도 생성 (프로그래매틱 접근용)
        json_path = self.summaries_dir / "index.json"
        json_path.write_text(
            json.dumps(index_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        logger.info(f"마스터 인덱스 생성: {md_path}, {json_path}")
        return md_path

    def _scan_directory(self, dir_path: Path) -> Dict[str, Any]:
        """디렉토리 스캔"""
        files = []
        for file_path in dir_path.glob("*.md"):
            if file_path.name == "index.md":
                continue

            file_info = {
                "name": file_path.name,
                "path": str(file_path.relative_to(self.summaries_dir)),
                "size": file_path.stat().st_size,
            }

            # YAML frontmatter 파싱
            frontmatter = self._parse_frontmatter(file_path)
            if frontmatter:
                file_info["metadata"] = frontmatter

            files.append(file_info)

        return {
            "count": len(files),
            "files": files
        }

    def _parse_frontmatter(self, file_path: Path) -> Optional[Dict]:
        """YAML frontmatter 파싱"""
        try:
            content = file_path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None

            end_idx = content.find("---", 3)
            if end_idx == -1:
                return None

            frontmatter_text = content[3:end_idx].strip()
            result = {}

            for line in frontmatter_text.split("\n"):
                if ":" in line and not line.strip().startswith("-"):
                    key, value = line.split(":", 1)
                    result[key.strip()] = value.strip()

            return result
        except Exception as e:
            logger.warning(f"Frontmatter 파싱 실패: {file_path} - {e}")
            return None

    def _build_search_index(self, directories: Dict) -> Dict[str, List[str]]:
        """검색 인덱스 생성

        키워드 → 파일 매핑
        """
        search_index = defaultdict(list)

        # 에러 코드 인덱싱
        if "error-codes" in directories:
            for file_info in directories["error-codes"]["files"]:
                metadata = file_info.get("metadata", {})
                module = metadata.get("module", "")
                range_str = metadata.get("range", "")

                if module:
                    search_index[module.lower()].append(file_info["path"])
                    search_index[module.upper()].append(file_info["path"])

                # 범위에서 숫자 추출 (예: "-5000 ~ -5999" → 5000, 5001, ..., 5999)
                # 모든 번호를 인덱싱하면 너무 크므로 대표 번호만
                if range_str:
                    import re
                    numbers = re.findall(r"\d+", range_str)
                    for num in numbers:
                        search_index[f"-{num}"].append(file_info["path"])
                        search_index[num].append(file_info["path"])

        # 용어 인덱싱
        if "glossary" in directories:
            for file_info in directories["glossary"]["files"]:
                # 파일명에서 letter 추출
                letter = file_info["name"].replace(".md", "")
                search_index[letter.lower()].append(file_info["path"])
                search_index[letter.upper()].append(file_info["path"])

        return dict(search_index)

    def _calculate_statistics(self, index_data: Dict) -> Dict[str, Any]:
        """통계 계산"""
        stats = {
            "total_files": 0,
            "by_type": {}
        }

        for dir_name, dir_info in index_data["directories"].items():
            count = dir_info.get("count", 0)
            stats["total_files"] += count
            stats["by_type"][dir_name] = count

        return stats

    def _generate_markdown_index(self, index_data: Dict) -> Path:
        """마크다운 마스터 인덱스 생성"""
        stats = index_data["statistics"]

        lines = [
            "---",
            "type: master-index",
            f"generated: {index_data['generated']}",
            f"version: {index_data['version']}",
            "---",
            "",
            "# OpenFrame 매뉴얼 요약본",
            "",
            "AI Agent를 위한 OpenFrame 문서 요약본입니다.",
            "",
            "## 빠른 검색 가이드",
            "",
            "### 에러 코드 검색",
            "```",
            "에러 코드 -5212 → error-codes/BASE-5000.md 참조",
            "에러 코드 -1001 → error-codes/BASE-1000.md 참조",
            "```",
            "",
            "### 용어 검색",
            "```",
            "TJES → glossary/T.md 참조",
            "TACF → glossary/T.md 참조",
            "```",
            "",
            "## 디렉토리 구조",
            "",
            "| 디렉토리 | 설명 | 파일 수 |",
            "|---------|------|--------|",
        ]

        dir_descriptions = {
            "error-codes": "에러 코드 사전",
            "glossary": "용어 사전",
            "products": "제품별 요약",
            "components": "컴포넌트 사전",
            "commands": "명령어 사전",
        }

        for dir_name, count in stats.get("by_type", {}).items():
            desc = dir_descriptions.get(dir_name, dir_name)
            lines.append(f"| [{dir_name}/]({dir_name}/index.md) | {desc} | {count} |")

        lines.extend([
            "",
            f"**총 {stats['total_files']}개 파일**",
            "",
            "## 사용 방법",
            "",
            "1. **에러 발생 시**: `error-codes/` 디렉토리에서 에러 번호로 검색",
            "2. **용어 확인 시**: `glossary/` 디렉토리에서 첫 글자로 검색",
            "3. **제품 정보 시**: `products/` 디렉토리에서 제품명으로 검색",
            "",
        ])

        md_path = self.summaries_dir / "index.md"
        md_path.write_text("\n".join(lines), encoding="utf-8")

        return md_path

    def rebuild_all(self) -> None:
        """모든 인덱스 재생성"""
        # 하위 인덱스들 재생성
        for subdir in ["error-codes", "glossary", "products"]:
            dir_path = self.summaries_dir / subdir
            if dir_path.exists():
                self._rebuild_subdir_index(dir_path)

        # 마스터 인덱스 재생성
        self.generate_master_index()

    def _rebuild_subdir_index(self, dir_path: Path) -> None:
        """하위 디렉토리 인덱스 재생성"""
        # 기존 index.md가 있으면 보존하고, 없으면 기본 생성
        index_path = dir_path / "index.md"
        if not index_path.exists():
            files = list(dir_path.glob("*.md"))
            content = f"# {dir_path.name}\n\n"
            content += f"총 {len(files)}개 파일\n\n"
            for f in sorted(files):
                if f.name != "index.md":
                    content += f"- [{f.name}]({f.name})\n"
            index_path.write_text(content, encoding="utf-8")
            logger.info(f"하위 인덱스 생성: {index_path}")
