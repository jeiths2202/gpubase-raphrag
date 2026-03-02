#!/usr/bin/env python3
"""
학습 데이터 강화 스크립트

요약본(commands/*.md)에서 명령어 상세 정보를 추출하여
learning_dataset.json을 강화합니다.

Features:
1. 요약본에서 명령어명, 설명, 구문 추출
2. 키워드 목록과 매칭하여 누락 항목 추가
3. 기존 항목의 syntax/parameters 보강
4. QLoRA 형식으로 변환 준비

Usage:
    python enrich_learning_data.py
    python enrich_learning_data.py --keywords docs/keyword.txt
    python enrich_learning_data.py --output enriched_dataset.json
"""

import re
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """프로젝트 루트 찾기"""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "CLAUDE.md").exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = get_project_root()


@dataclass
class CommandEntry:
    """명령어 항목"""
    name: str
    description: str
    syntax: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    related: List[str] = field(default_factory=list)
    source_file: str = ""
    product: str = ""
    item_type: str = "command"


@dataclass
class EnrichmentStats:
    """강화 통계"""
    total_summaries_processed: int = 0
    commands_extracted: int = 0
    existing_items_enriched: int = 0
    new_items_added: int = 0
    keywords_matched: int = 0
    by_product: Dict[str, int] = field(default_factory=dict)


class SummaryParser:
    """요약본 Markdown 파서"""

    # 명령어 섹션 패턴
    COMMAND_HEADER = re.compile(r'^##\s+(.+?)$', re.MULTILINE)
    SYNTAX_BLOCK = re.compile(r'\*\*구문:\*\*\s*\n```\n?([\s\S]*?)\n?```', re.MULTILINE)
    SOURCE_LINE = re.compile(r'-\s*소스:\s*(.+?)(?:\n|$)')

    def __init__(self):
        self.stats = EnrichmentStats()

    def parse_summary_file(self, file_path: Path) -> List[CommandEntry]:
        """단일 요약본 파일 파싱"""
        commands = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"파일 읽기 실패: {file_path}: {e}")
            return commands

        # 제품명 추출 (파일명에서)
        product = self._extract_product(file_path.stem)

        # 제목 라인 추출 (첫 번째 # 헤더)
        title_match = re.search(r'^#\s+(.+?)$', content, re.MULTILINE)
        file_title = title_match.group(1) if title_match else file_path.stem

        # 명령어 섹션 분리
        sections = re.split(r'\n---\n', content)

        for section in sections:
            # ## 헤더 찾기
            header_match = self.COMMAND_HEADER.search(section)
            if not header_match:
                continue

            name = header_match.group(1).strip()

            # 설명 추출 (헤더 다음 줄부터 **구문:** 또는 - 소스: 이전까지)
            header_end = header_match.end()
            remaining = section[header_end:].strip()

            # 구문 블록 찾기
            syntax_match = self.SYNTAX_BLOCK.search(remaining)
            syntax = syntax_match.group(1).strip() if syntax_match else None

            # 소스 찾기
            source_match = self.SOURCE_LINE.search(remaining)
            source = source_match.group(1).strip() if source_match else ""

            # 설명 추출 (구문 블록 이전)
            if syntax_match:
                desc_end = remaining.find('**구문:**')
            elif source_match:
                desc_end = remaining.find('- 소스:')
            else:
                desc_end = len(remaining)

            description = remaining[:desc_end].strip() if desc_end > 0 else ""

            # 빈 항목 스킵
            if not name or (not description and not syntax):
                continue

            # 파라미터 추출 (구문에서)
            parameters = self._extract_parameters(syntax) if syntax else []

            cmd = CommandEntry(
                name=name,
                description=description,
                syntax=syntax,
                parameters=parameters,
                source_file=source if source else str(file_path.name),
                product=product,
                item_type="command"
            )
            commands.append(cmd)

        self.stats.total_summaries_processed += 1
        self.stats.commands_extracted += len(commands)

        if product:
            self.stats.by_product[product] = self.stats.by_product.get(product, 0) + len(commands)

        return commands

    def _extract_product(self, filename: str) -> str:
        """파일명에서 제품명 추출"""
        # OpenFrame_TJES_MVS -> OF_TJES
        # Tibero -> Tibero
        # Tmax -> Tmax

        if filename.startswith("OpenFrame_"):
            parts = filename.replace("OpenFrame_", "").split("_")
            if parts:
                return f"OF_{parts[0]}"
        elif filename.startswith("OF_"):
            parts = filename.replace("OF_", "").split("_")
            if parts:
                return f"OF_{parts[0]}"
        elif filename in ["Tibero", "Tmax", "JEUS", "WebtoB"]:
            return filename
        elif filename.startswith("Tibero"):
            return "Tibero"
        elif filename.startswith("Tmax"):
            return "Tmax"
        elif filename.startswith("JEUS"):
            return "JEUS"

        return "Unknown"

    def _extract_parameters(self, syntax: str) -> List[str]:
        """구문에서 파라미터 추출"""
        if not syntax:
            return []

        params = []

        # <param-name> 패턴
        angle_params = re.findall(r'<([^>]+)>', syntax)
        params.extend(angle_params)

        # [optional] 패턴
        bracket_params = re.findall(r'\[([^\]]+)\]', syntax)
        for p in bracket_params:
            if '=' in p or not p.startswith('-'):
                params.append(f"[{p}]")

        # KEY=value 패턴
        key_value = re.findall(r'\b([A-Z][A-Z0-9_]*)\s*=', syntax)
        params.extend(key_value)

        return list(set(params))[:10]  # 최대 10개


class LearningDataEnricher:
    """학습 데이터 강화 클래스"""

    def __init__(
        self,
        summaries_dir: Path,
        learning_data_path: Path,
        keywords_path: Optional[Path] = None,
    ):
        self.summaries_dir = summaries_dir
        self.learning_data_path = learning_data_path
        self.keywords_path = keywords_path

        self.parser = SummaryParser()
        self.existing_data: Dict[str, Any] = {}
        self.enriched_items: List[Dict[str, Any]] = []
        self.keywords: Set[str] = set()

        # 기존 항목 인덱스 (name -> item)
        self.name_index: Dict[str, Dict] = {}

    def load_keywords(self) -> Set[str]:
        """키워드 파일 로드"""
        if not self.keywords_path or not self.keywords_path.exists():
            return set()

        keywords = set()
        with open(self.keywords_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    keywords.add(line)

        logger.info(f"키워드 {len(keywords)}개 로드됨")
        return keywords

    def load_existing_data(self) -> Dict[str, Any]:
        """기존 학습 데이터 로드"""
        if not self.learning_data_path.exists():
            return {"metadata": {}, "items": []}

        with open(self.learning_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 이름 인덱스 구축
        for item in data.get("items", []):
            name = item.get("name", "")
            if name:
                self.name_index[name.lower()] = item

        logger.info(f"기존 항목 {len(data.get('items', []))}개 로드됨")
        return data

    def parse_all_summaries(self) -> List[CommandEntry]:
        """모든 요약본 파싱"""
        all_commands = []

        # commands 디렉토리
        commands_dir = self.summaries_dir / "commands"
        if commands_dir.exists():
            for md_file in commands_dir.glob("*.md"):
                if md_file.name == "index.md":
                    continue
                commands = self.parser.parse_summary_file(md_file)
                all_commands.extend(commands)
                if len(commands) > 0:
                    logger.debug(f"  {md_file.name}: {len(commands)}개 명령어")

        # configs 디렉토리
        configs_dir = self.summaries_dir / "configs"
        if configs_dir.exists():
            for md_file in configs_dir.glob("*.md"):
                if md_file.name == "index.md":
                    continue
                configs = self.parser.parse_summary_file(md_file)
                for cfg in configs:
                    cfg.item_type = "config"
                all_commands.extend(configs)

        # apis 디렉토리
        apis_dir = self.summaries_dir / "apis"
        if apis_dir.exists():
            for md_file in apis_dir.glob("*.md"):
                if md_file.name == "index.md":
                    continue
                apis = self.parser.parse_summary_file(md_file)
                for api in apis:
                    api.item_type = "api"
                all_commands.extend(apis)

        logger.info(f"요약본에서 총 {len(all_commands)}개 항목 추출")
        return all_commands

    def enrich_existing_item(self, item: Dict, cmd: CommandEntry) -> bool:
        """기존 항목 강화"""
        changed = False

        # syntax가 비어있으면 채우기
        if not item.get("syntax") and cmd.syntax:
            item["syntax"] = cmd.syntax
            changed = True

        # parameters가 비어있으면 채우기
        if not item.get("parameters") and cmd.parameters:
            item["parameters"] = cmd.parameters
            changed = True

        # description이 짧으면 보강
        existing_desc = item.get("description", "")
        if len(existing_desc) < 50 and len(cmd.description) > len(existing_desc):
            item["description"] = cmd.description
            changed = True

        # product가 없으면 추가
        if not item.get("product") and cmd.product:
            item["product"] = cmd.product
            changed = True

        return changed

    def create_new_item(self, cmd: CommandEntry) -> Dict[str, Any]:
        """새 학습 항목 생성"""
        return {
            "name": cmd.name,
            "type": cmd.item_type,
            "description": cmd.description,
            "syntax": cmd.syntax,
            "parameters": cmd.parameters,
            "examples": cmd.examples,
            "related": cmd.related,
            "source_file": cmd.source_file,
            "product": cmd.product,
        }

    def enrich(self) -> Dict[str, Any]:
        """학습 데이터 강화 실행"""
        # 1. 데이터 로드
        self.keywords = self.load_keywords()
        self.existing_data = self.load_existing_data()

        # 2. 요약본 파싱
        commands = self.parse_all_summaries()

        # 3. 기존 데이터 강화 및 새 항목 추가
        existing_items = self.existing_data.get("items", [])
        new_items = []
        enriched_count = 0

        for cmd in commands:
            name_lower = cmd.name.lower()

            # 기존 항목 찾기
            if name_lower in self.name_index:
                existing_item = self.name_index[name_lower]
                if self.enrich_existing_item(existing_item, cmd):
                    enriched_count += 1
            else:
                # 새 항목 추가
                new_item = self.create_new_item(cmd)
                new_items.append(new_item)
                self.name_index[name_lower] = new_item

        self.parser.stats.existing_items_enriched = enriched_count
        self.parser.stats.new_items_added = len(new_items)

        # 4. 키워드 기반 추가 (요약본에 없는 키워드)
        keyword_items = self._create_keyword_items()
        new_items.extend(keyword_items)

        # 5. 결과 병합
        all_items = existing_items + new_items

        # 6. 통계 업데이트
        type_stats = defaultdict(int)
        product_stats = defaultdict(int)

        for item in all_items:
            type_stats[item.get("type", "unknown")] += 1
            product_stats[item.get("product", "Unknown")] += 1

        result = {
            "metadata": {
                "total_items": len(all_items),
                "type_stats": dict(type_stats),
                "product_stats": dict(product_stats),
                "enrichment_date": datetime.now().isoformat(),
                "enrichment_stats": {
                    "summaries_processed": self.parser.stats.total_summaries_processed,
                    "commands_extracted": self.parser.stats.commands_extracted,
                    "existing_enriched": enriched_count,
                    "new_added": len(new_items),
                    "keywords_used": len(self.keywords),
                }
            },
            "items": all_items
        }

        return result

    def _create_keyword_items(self) -> List[Dict[str, Any]]:
        """키워드 기반 항목 생성 (요약본에 없는 것들)"""
        if not self.keywords:
            return []

        new_items = []

        # 기술 키워드 패턴 (명령어, 설정, API 등)
        command_pattern = re.compile(r'^[a-z][a-z0-9_]*mgr$|^[a-z]{2,}run$|^[a-z]{2,}ctl$', re.IGNORECASE)
        config_pattern = re.compile(r'\.conf$|\.cfg$|\.properties$', re.IGNORECASE)
        api_pattern = re.compile(r'^[A-Z]+_[A-Z0-9_]+$|^tp[a-z]+$|^tx[a-z]+$')

        for keyword in self.keywords:
            # 이미 있는 항목 스킵
            if keyword.lower() in self.name_index:
                continue

            # 짧은 약어(2글자 이하) 스킵
            if len(keyword) <= 2:
                continue

            # 타입 결정
            if command_pattern.match(keyword):
                item_type = "command"
                desc = f"{keyword}は、OpenFrameシステムの管理コマンドです。"
            elif config_pattern.search(keyword):
                item_type = "config"
                desc = f"{keyword}は、設定ファイルです。"
            elif api_pattern.match(keyword):
                item_type = "api"
                desc = f"{keyword}は、APIまたは関数です。"
            else:
                # 일반 키워드는 스킵 (너무 많음)
                continue

            new_item = {
                "name": keyword,
                "type": item_type,
                "description": desc,
                "syntax": None,
                "parameters": [],
                "examples": [],
                "related": [],
                "source_file": "keyword_extraction",
                "product": "Unknown",
            }
            new_items.append(new_item)
            self.name_index[keyword.lower()] = new_item
            self.parser.stats.keywords_matched += 1

        return new_items

    def save(self, result: Dict[str, Any], output_path: Path) -> None:
        """결과 저장"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"저장 완료: {output_path}")
        logger.info(f"총 항목: {result['metadata']['total_items']}")


def main():
    parser = argparse.ArgumentParser(description="학습 데이터 강화")
    parser.add_argument(
        "--summaries",
        type=Path,
        default=PROJECT_ROOT / "uploads" / "summaries",
        help="요약본 디렉토리"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "uploads" / "summaries" / "learning_dataset.json",
        help="기존 학습 데이터"
    )
    parser.add_argument(
        "--keywords",
        type=Path,
        default=PROJECT_ROOT / "docs" / "keyword.txt",
        help="키워드 파일"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "uploads" / "summaries" / "enriched_learning_dataset.json",
        help="출력 파일"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("학습 데이터 강화 시작")
    logger.info(f"요약본: {args.summaries}")
    logger.info(f"기존 데이터: {args.input}")
    logger.info(f"키워드: {args.keywords}")
    logger.info(f"출력: {args.output}")
    logger.info("=" * 60)

    enricher = LearningDataEnricher(
        summaries_dir=args.summaries,
        learning_data_path=args.input,
        keywords_path=args.keywords,
    )

    result = enricher.enrich()
    enricher.save(result, args.output)

    # 통계 출력
    stats = enricher.parser.stats
    logger.info("\n" + "=" * 60)
    logger.info("강화 통계:")
    logger.info(f"  요약본 처리: {stats.total_summaries_processed}개")
    logger.info(f"  명령어 추출: {stats.commands_extracted}개")
    logger.info(f"  기존 항목 강화: {stats.existing_items_enriched}개")
    logger.info(f"  새 항목 추가: {stats.new_items_added}개")
    logger.info(f"  키워드 매칭: {stats.keywords_matched}개")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    exit(main())
