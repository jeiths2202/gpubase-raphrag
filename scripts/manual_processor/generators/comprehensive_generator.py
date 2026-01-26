"""
Comprehensive Markdown Generator

추출된 모든 항목을 체계적인 마크다운 파일로 생성합니다.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict

from ..parsers.comprehensive_parser import ExtractedItem

logger = logging.getLogger(__name__)


class ComprehensiveGenerator:
    """포괄적인 마크다운 생성기"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

        # 출력 디렉토리 구조
        self.dirs = {
            "commands": output_dir / "commands",
            "configs": output_dir / "configs",
            "apis": output_dir / "apis",
            "concepts": output_dir / "concepts",
            "procedures": output_dir / "procedures",
        }

        # 디렉토리 생성
        for dir_path in self.dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)

    def generate_all(self, items: List[ExtractedItem]) -> Dict[str, int]:
        """모든 마크다운 파일 생성"""
        stats = {
            "commands": 0,
            "configs": 0,
            "apis": 0,
            "concepts": 0,
            "procedures": 0,
        }

        # 항목을 타입별로 분류
        by_type = defaultdict(list)
        for item in items:
            by_type[item.item_type].append(item)

        # 각 타입별 생성
        stats["commands"] = self._generate_commands(by_type.get("command", []))
        stats["configs"] = self._generate_configs(by_type.get("config", []))
        stats["apis"] = self._generate_apis(by_type.get("api", []))
        stats["concepts"] = self._generate_concepts(by_type.get("concept", []))
        stats["procedures"] = self._generate_procedures(by_type.get("procedure", []))

        # 통합 인덱스 생성
        self._generate_master_index(items, stats)

        # JSON 인덱스 생성 (검색 서비스용)
        self._generate_json_index(items)

        return stats

    def _generate_commands(self, items: List[ExtractedItem]) -> int:
        """명령어 마크다운 생성

        동일 명령어가 여러 제품(MSP/MVS/VOS3/XSP)에 있으면 통합 표시
        """
        if not items:
            return 0

        # 첫 글자별로 분류
        by_letter = defaultdict(list)
        for item in items:
            first_letter = item.name[0].upper()
            if not first_letter.isalpha():
                first_letter = "OTHER"
            by_letter[first_letter].append(item)

        # 각 글자별 파일 생성 (멀티 제품 지원)
        for letter, letter_items in by_letter.items():
            self._write_commands_file(
                self.dirs["commands"] / f"{letter}.md",
                f"Commands - {letter}",
                "명령어/유틸리티",
                letter_items
            )

        # 인덱스 생성
        self._write_index(
            self.dirs["commands"] / "index.md",
            "Commands Index",
            "명령어/유틸리티 인덱스",
            by_letter
        )

        return len(items)

    def _write_commands_file(
        self,
        file_path: Path,
        title: str,
        description: str,
        items: List[ExtractedItem]
    ):
        """명령어 파일 작성 (동일 명령어의 여러 제품 버전 통합)"""
        # 이름별로 그룹화
        by_name = defaultdict(list)
        for item in items:
            by_name[item.name.lower()].append(item)

        lines = [
            "---",
            "type: command",
            f"count: {len(by_name)}",
            f"generated: {datetime.now().isoformat()}",
            "---",
            "",
            f"# {title}",
            "",
            f"{description} ({len(by_name)}개 명령어)",
            "",
        ]

        for name in sorted(by_name.keys()):
            cmd_items = by_name[name]
            lines.extend(self._format_multi_product_command(name, cmd_items))
            lines.append("")

        file_path.write_text("\n".join(lines), encoding="utf-8")

    def _format_multi_product_command(
        self, name: str, items: List[ExtractedItem]
    ) -> List[str]:
        """여러 제품 버전의 명령어 포맷팅"""
        lines = [f"## {name}"]

        # 제품별로 정렬 (MSP, MVS, VOS3, XSP 순)
        product_order = {"MSP": 1, "MVS": 2, "VOS3": 3, "XSP": 4, "Batch": 5}
        items = sorted(items, key=lambda x: product_order.get(x.product, 99))

        products = [item.product for item in items if item.product]
        if products:
            lines.append(f"- **지원 제품**: {', '.join(set(products))}")

        # 각 제품별 정보 표시
        for item in items:
            if len(items) > 1 and item.product:
                lines.append(f"")
                lines.append(f"### {item.product}")

            if item.description:
                # 설명에서 노이즈 제거
                desc = self._clean_description(item.description)
                if desc:
                    lines.append(f"- **설명**: {desc[:300]}{'...' if len(desc) > 300 else ''}")

            if item.syntax:
                lines.append(f"- **구문**: `{item.syntax[:200]}`")

            if item.parameters:
                lines.append("- **파라미터**:")
                for param in item.parameters[:5]:
                    if isinstance(param, dict):
                        for k, v in param.items():
                            lines.append(f"  - {k}: {v}")

            if item.examples:
                lines.append("- **예제**:")
                for ex in item.examples[:2]:
                    lines.append(f"  ```")
                    lines.append(f"  {ex[:200]}")
                    lines.append(f"  ```")

            lines.append(f"- **참조**: {item.source_file} (p.{item.source_page})")

        return lines

    def _clean_description(self, description: str) -> str:
        """설명에서 노이즈 제거"""
        import re

        # 다른 명령어 설명이 섞여있으면 첫 번째 문장만 추출
        # 패턴: 명령어이름 + 줄바꿈 + 새 설명
        parts = re.split(r'\n[a-z]{3,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd)\s*\n', description, flags=re.IGNORECASE)
        if parts:
            description = parts[0]

        # 테이블 헤더 제거
        description = re.sub(r'^(?:説明|ツール|Description|Tool)\s*\n?', '', description)

        # 연속된 공백 정리
        description = ' '.join(description.split())

        return description.strip()

    def _generate_configs(self, items: List[ExtractedItem]) -> int:
        """설정 파라미터 마크다운 생성"""
        if not items:
            return 0

        # 제품별로 분류
        by_product = defaultdict(list)
        for item in items:
            by_product[item.product or "General"].append(item)

        for product, product_items in by_product.items():
            safe_name = product.replace(" ", "_").replace("/", "_")
            self._write_items_file(
                self.dirs["configs"] / f"{safe_name}.md",
                f"Configuration - {product}",
                f"{product} 설정 파라미터",
                product_items,
                "config"
            )

        # 인덱스 생성
        self._write_product_index(
            self.dirs["configs"] / "index.md",
            "Configuration Index",
            "설정 파라미터 인덱스",
            by_product
        )

        return len(items)

    def _generate_apis(self, items: List[ExtractedItem]) -> int:
        """API/함수 마크다운 생성"""
        if not items:
            return 0

        # 제품별로 분류
        by_product = defaultdict(list)
        for item in items:
            by_product[item.product or "General"].append(item)

        for product, product_items in by_product.items():
            safe_name = product.replace(" ", "_").replace("/", "_")
            self._write_items_file(
                self.dirs["apis"] / f"{safe_name}.md",
                f"API Reference - {product}",
                f"{product} API/함수",
                product_items,
                "api"
            )

        # 인덱스 생성
        self._write_product_index(
            self.dirs["apis"] / "index.md",
            "API Index",
            "API/함수 인덱스",
            by_product
        )

        return len(items)

    def _generate_concepts(self, items: List[ExtractedItem]) -> int:
        """개념/정의 마크다운 생성"""
        if not items:
            return 0

        # 첫 글자별로 분류
        by_letter = defaultdict(list)
        for item in items:
            first_letter = item.name[0].upper()
            if not first_letter.isalpha():
                first_letter = "OTHER"
            by_letter[first_letter].append(item)

        for letter, letter_items in by_letter.items():
            self._write_items_file(
                self.dirs["concepts"] / f"{letter}.md",
                f"Concepts - {letter}",
                "개념/정의",
                letter_items,
                "concept"
            )

        # 인덱스 생성
        self._write_index(
            self.dirs["concepts"] / "index.md",
            "Concepts Index",
            "개념/정의 인덱스",
            by_letter
        )

        return len(items)

    def _generate_procedures(self, items: List[ExtractedItem]) -> int:
        """프로시저 마크다운 생성"""
        if not items:
            return 0

        # 제품별로 분류
        by_product = defaultdict(list)
        for item in items:
            by_product[item.product or "General"].append(item)

        for product, product_items in by_product.items():
            safe_name = product.replace(" ", "_").replace("/", "_")
            self._write_items_file(
                self.dirs["procedures"] / f"{safe_name}.md",
                f"Procedures - {product}",
                f"{product} 절차/가이드",
                product_items,
                "procedure"
            )

        # 인덱스 생성
        self._write_product_index(
            self.dirs["procedures"] / "index.md",
            "Procedures Index",
            "절차/가이드 인덱스",
            by_product
        )

        return len(items)

    def _write_items_file(
        self,
        file_path: Path,
        title: str,
        description: str,
        items: List[ExtractedItem],
        item_type: str
    ):
        """항목 파일 작성"""
        # 이름순 정렬
        items = sorted(items, key=lambda x: x.name.lower())

        lines = [
            "---",
            f"type: {item_type}",
            f"count: {len(items)}",
            f"generated: {datetime.now().isoformat()}",
            "---",
            "",
            f"# {title}",
            "",
            f"{description} ({len(items)}개 항목)",
            "",
        ]

        for item in items:
            lines.extend(self._format_item(item, item_type))
            lines.append("")

        file_path.write_text("\n".join(lines), encoding="utf-8")

    def _format_item(self, item: ExtractedItem, item_type: str) -> List[str]:
        """항목 포맷팅"""
        lines = [f"## {item.name}"]

        if item.product:
            lines.append(f"- **제품**: {item.product}")

        if item.description:
            lines.append(f"- **설명**: {item.description[:300]}{'...' if len(item.description) > 300 else ''}")

        if item.syntax:
            lines.append(f"- **구문**: `{item.syntax[:200]}`")

        if item.parameters:
            lines.append("- **파라미터**:")
            for param in item.parameters[:5]:
                if isinstance(param, dict):
                    for k, v in param.items():
                        lines.append(f"  - {k}: {v}")

        if item.examples:
            lines.append("- **예제**:")
            for ex in item.examples[:2]:
                lines.append(f"  ```")
                lines.append(f"  {ex[:200]}")
                lines.append(f"  ```")

        lines.append(f"- **참조**: {item.source_file} (p.{item.source_page})")

        return lines

    def _write_index(
        self,
        file_path: Path,
        title: str,
        description: str,
        by_letter: Dict[str, List[ExtractedItem]]
    ):
        """알파벳순 인덱스 작성"""
        total = sum(len(items) for items in by_letter.values())

        lines = [
            "---",
            "type: index",
            f"total: {total}",
            f"generated: {datetime.now().isoformat()}",
            "---",
            "",
            f"# {title}",
            "",
            f"{description} (총 {total}개 항목)",
            "",
            "## 알파벳순",
            "",
        ]

        for letter in sorted(by_letter.keys()):
            items = by_letter[letter]
            lines.append(f"### [{letter}]({letter}.md) ({len(items)}개)")
            for item in sorted(items, key=lambda x: x.name.lower())[:10]:
                lines.append(f"- {item.name}")
            if len(items) > 10:
                lines.append(f"- ... 외 {len(items) - 10}개")
            lines.append("")

        file_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_product_index(
        self,
        file_path: Path,
        title: str,
        description: str,
        by_product: Dict[str, List[ExtractedItem]]
    ):
        """제품별 인덱스 작성"""
        total = sum(len(items) for items in by_product.values())

        lines = [
            "---",
            "type: index",
            f"total: {total}",
            f"generated: {datetime.now().isoformat()}",
            "---",
            "",
            f"# {title}",
            "",
            f"{description} (총 {total}개 항목)",
            "",
            "## 제품별",
            "",
        ]

        for product in sorted(by_product.keys()):
            items = by_product[product]
            safe_name = product.replace(" ", "_").replace("/", "_")
            lines.append(f"### [{product}]({safe_name}.md) ({len(items)}개)")
            for item in sorted(items, key=lambda x: x.name.lower())[:10]:
                lines.append(f"- {item.name}")
            if len(items) > 10:
                lines.append(f"- ... 외 {len(items) - 10}개")
            lines.append("")

        file_path.write_text("\n".join(lines), encoding="utf-8")

    def _generate_master_index(self, items: List[ExtractedItem], stats: Dict[str, int]):
        """마스터 인덱스 생성"""
        total = len(items)

        lines = [
            "---",
            "type: master-index",
            f"generated: {datetime.now().isoformat()}",
            "version: 2.0",
            "---",
            "",
            "# OpenFrame 매뉴얼 요약본 v2.0",
            "",
            "AI Agent를 위한 OpenFrame 문서 포괄적 요약본입니다.",
            "",
            "## 통계",
            "",
            f"| 카테고리 | 항목 수 |",
            f"|----------|---------|",
            f"| [에러 코드](error-codes/index.md) | 기존 |",
            f"| [용어 사전](glossary/index.md) | 기존 |",
            f"| [명령어/유틸리티](commands/index.md) | {stats['commands']} |",
            f"| [설정 파라미터](configs/index.md) | {stats['configs']} |",
            f"| [API/함수](apis/index.md) | {stats['apis']} |",
            f"| [개념/정의](concepts/index.md) | {stats['concepts']} |",
            f"| [절차/가이드](procedures/index.md) | {stats['procedures']} |",
            "",
            f"**총 {total}개 항목** (에러 코드, 용어 사전 제외)",
            "",
            "## 빠른 검색 가이드",
            "",
            "### 명령어 검색",
            "```",
            "tjesinit → commands/T.md 참조",
            "oscboot → commands/O.md 참조",
            "```",
            "",
            "### 설정 검색",
            "```",
            "TJES_* → configs/Batch.md 참조",
            "OSC_* → configs/OSC.md 참조",
            "```",
            "",
            "## 사용 방법",
            "",
            "1. **명령어 검색**: `commands/` 디렉토리에서 첫 글자로 검색",
            "2. **설정 검색**: `configs/` 디렉토리에서 제품명으로 검색",
            "3. **개념 검색**: `concepts/` 디렉토리에서 첫 글자로 검색",
            "4. **에러 코드**: `error-codes/` 디렉토리에서 번호 범위로 검색",
            "5. **용어**: `glossary/` 디렉토리에서 첫 글자로 검색",
            "",
        ]

        (self.output_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")

    def _generate_json_index(self, items: List[ExtractedItem]):
        """JSON 인덱스 생성 (검색 서비스용)"""
        index = {
            "version": "2.0",
            "generated": datetime.now().isoformat(),
            "total_items": len(items),
            "items": {}
        }

        for item in items:
            key = item.name.lower()
            if key not in index["items"]:
                index["items"][key] = []

            index["items"][key].append({
                "name": item.name,
                "type": item.item_type,
                "description": item.description[:200],
                "product": item.product,
                "source": item.source_file,
                "page": item.source_page
            })

        # 기존 인덱스와 병합
        existing_index_path = self.output_dir / "index.json"
        if existing_index_path.exists():
            try:
                existing = json.loads(existing_index_path.read_text(encoding="utf-8"))
                # 기존 에러 코드와 용어 유지
                if "error_codes" in existing:
                    index["error_codes"] = existing["error_codes"]
                if "glossary" in existing:
                    index["glossary"] = existing["glossary"]
            except:
                pass

        (self.output_dir / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
