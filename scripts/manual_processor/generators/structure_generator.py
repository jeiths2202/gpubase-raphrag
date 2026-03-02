"""
구조 출력 생성기

DocumentStructure를 JSON 및 Markdown 파일로 출력합니다.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from ..models.document_structure import (
    DocumentStructure, HierarchyNode, ImageReference
)

logger = logging.getLogger(__name__)


class StructureGenerator:
    """문서 구조 출력 생성기

    DocumentStructure 객체를 다양한 형식(JSON, Markdown)으로 출력합니다.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.structures_dir = output_dir / "structures"
        self.structures_dir.mkdir(parents=True, exist_ok=True)

    def generate_all(self, structure: DocumentStructure) -> Dict[str, Path]:
        """모든 출력 파일 생성

        Args:
            structure: DocumentStructure 객체

        Returns:
            생성된 파일 경로 딕셔너리
        """
        # 기본 파일명 (확장자 제외)
        base_name = Path(structure.file_name).stem

        # 타임스탬프 추가
        structure.generated_at = datetime.now()

        output_files = {}

        # 1. JSON 구조 파일
        json_path = self._generate_json(structure, base_name)
        output_files["structure_json"] = json_path

        # 2. Markdown 요약 파일
        md_path = self._generate_markdown(structure, base_name)
        output_files["structure_md"] = md_path

        # 3. 이미지 인덱스 JSON
        images_path = self._generate_images_index(structure, base_name)
        output_files["images_json"] = images_path

        # 4. 검증 결과 JSON
        validation_path = self._generate_validation(structure, base_name)
        output_files["validation_json"] = validation_path

        logger.info(f"구조 파일 생성 완료: {base_name}")
        for key, path in output_files.items():
            logger.info(f"  - {key}: {path.name}")

        return output_files

    def _generate_json(self, structure: DocumentStructure, base_name: str) -> Path:
        """JSON 구조 파일 생성"""
        output_path = self.structures_dir / f"{base_name}_structure.json"

        data = structure.to_dict()

        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return output_path

    def _generate_markdown(self, structure: DocumentStructure, base_name: str) -> Path:
        """Markdown 요약 파일 생성"""
        output_path = self.structures_dir / f"{base_name}_structure.md"

        lines = [
            "---",
            f"title: {structure.title}",
            f"file: {structure.file_name}",
            f"pages: {structure.total_pages}",
            f"language: {structure.language}",
            f"generated: {structure.generated_at.isoformat() if structure.generated_at else ''}",
            f"valid: {structure.is_valid()}",
            "---",
            "",
            f"# {structure.title}",
            "",
            "## 문서 정보",
            "",
            f"- **파일명**: {structure.file_name}",
            f"- **총 페이지**: {structure.total_pages}",
            f"- **언어**: {structure.language}",
            f"- **노드 수**: {structure.count_all_nodes()}",
            f"- **이미지 수**: {len(structure.images_index)}",
            "",
        ]

        # 검증 결과
        if structure.validation:
            lines.extend([
                "## 검증 결과",
                "",
                f"- **TOC 항목**: {structure.validation.get('toc_items', 0)}",
                f"- **추출 항목**: {structure.validation.get('extracted_items', 0)}",
                f"- **매칭 항목**: {structure.validation.get('matched_items', 0)}",
                f"- **커버리지**: {structure.validation.get('coverage_ratio', 0) * 100:.1f}%",
                f"- **유효성**: {'통과' if structure.is_valid() else '실패'}",
                "",
            ])

            if structure.validation.get("missing_items"):
                lines.append("### 누락된 항목")
                lines.append("")
                for item in structure.validation["missing_items"][:5]:
                    lines.append(f"- {item}")
                lines.append("")

        # 목차 (계층 구조)
        lines.extend([
            "## 목차",
            "",
        ])

        for node in structure.hierarchy:
            self._append_toc_node(lines, node, 0)

        lines.append("")

        # 상세 구조
        lines.extend([
            "## 상세 구조",
            "",
        ])

        for node in structure.hierarchy:
            self._append_detail_node(lines, node, 1)

        # 이미지 목록
        if structure.images_index:
            lines.extend([
                "## 이미지 및 표 목록",
                "",
                "| 타입 | ID | 페이지 | 캡션 |",
                "|------|----|----|------|",
            ])

            for img in structure.images_index[:50]:  # 최대 50개
                caption = img.caption[:50] + "..." if len(img.caption) > 50 else img.caption
                lines.append(f"| {img.ref_type} | {img.ref_id} | {img.page_number} | {caption} |")

            if len(structure.images_index) > 50:
                lines.append(f"\n*... 외 {len(structure.images_index) - 50}개*")

            lines.append("")

        # 키워드
        all_keywords = structure.get_all_keywords()
        if all_keywords:
            lines.extend([
                "## 키워드",
                "",
                ", ".join(all_keywords[:30]),
                "",
            ])

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    def _append_toc_node(
        self, lines: List[str], node: HierarchyNode, depth: int
    ) -> None:
        """목차 노드 추가 (재귀적)"""
        indent = "  " * depth
        icon = self._get_node_icon(node)
        page_info = f" (p.{node.page_start}"
        if node.page_end and node.page_end != node.page_start:
            page_info += f"-{node.page_end}"
        page_info += ")"

        lines.append(f"{indent}- {icon} **{node.title}**{page_info}")

        for child in node.children:
            self._append_toc_node(lines, child, depth + 1)

    def _append_detail_node(
        self, lines: List[str], node: HierarchyNode, heading_level: int
    ) -> None:
        """상세 노드 추가 (재귀적)"""
        heading = "#" * min(heading_level, 6)
        icon = self._get_node_icon(node)

        lines.append(f"{heading} {icon} {node.title}")
        lines.append("")

        # 메타 정보
        lines.append(f"- **ID**: `{node.id}`")
        lines.append(f"- **페이지**: {node.page_start}-{node.page_end}")
        lines.append(f"- **타입**: {node.node_type.value}")

        if node.keywords:
            lines.append(f"- **키워드**: {', '.join(node.keywords)}")

        if node.has_images:
            lines.append(f"- **이미지**: {len(node.images)}개")

        lines.append("")

        # 요약
        if node.summary:
            lines.append(f"> {node.summary}")
            lines.append("")

        # 이미지 목록
        if node.images:
            lines.append("**포함된 이미지/표:**")
            for img in node.images[:5]:
                lines.append(f"- [{img.ref_type}] {img.ref_id}: {img.caption[:50]}")
            if len(node.images) > 5:
                lines.append(f"- *... 외 {len(node.images) - 5}개*")
            lines.append("")

        # 자식 노드
        for child in node.children:
            self._append_detail_node(lines, child, heading_level + 1)

    def _get_node_icon(self, node: HierarchyNode) -> str:
        """노드 타입에 따른 아이콘"""
        icons = {
            "chapter": "",
            "section": "",
            "subsection": "",
            "paragraph": "",
            "appendix": "",
        }
        return icons.get(node.node_type.value, "")

    def _generate_images_index(
        self, structure: DocumentStructure, base_name: str
    ) -> Path:
        """이미지 인덱스 JSON 생성"""
        output_path = self.structures_dir / f"{base_name}_images.json"

        data = {
            "file_name": structure.file_name,
            "total_images": len(structure.images_index),
            "figures": [],
            "tables": [],
            "by_page": {},
        }

        for img in structure.images_index:
            img_data = img.to_dict()

            if img.ref_type == "figure":
                data["figures"].append(img_data)
            else:
                data["tables"].append(img_data)

            # 페이지별 인덱스
            page_key = str(img.page_number)
            if page_key not in data["by_page"]:
                data["by_page"][page_key] = []
            data["by_page"][page_key].append(img_data)

        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return output_path

    def _generate_validation(
        self, structure: DocumentStructure, base_name: str
    ) -> Path:
        """검증 결과 JSON 생성"""
        output_path = self.structures_dir / f"{base_name}_validation.json"

        data = {
            "file_name": structure.file_name,
            "generated_at": structure.generated_at.isoformat() if structure.generated_at else None,
            "validation": structure.validation,
            "statistics": {
                "total_pages": structure.total_pages,
                "total_nodes": structure.count_all_nodes(),
                "total_images": len(structure.images_index),
                "chapters": len([n for n in structure.hierarchy if n.node_type.value == "chapter"]),
                "appendices": len([n for n in structure.hierarchy if n.node_type.value == "appendix"]),
                "sections": len(structure.get_nodes_at_level(2)),
                "subsections": len(structure.get_nodes_at_level(3)),
            },
            "keywords_summary": structure.get_all_keywords()[:20],
        }

        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return output_path


def generate_batch_index(
    output_dir: Path, structures: List[DocumentStructure]
) -> Path:
    """여러 문서의 통합 인덱스 생성

    Args:
        output_dir: 출력 디렉토리
        structures: DocumentStructure 목록

    Returns:
        인덱스 파일 경로
    """
    structures_dir = output_dir / "structures"
    structures_dir.mkdir(parents=True, exist_ok=True)

    index_path = structures_dir / "index.json"

    documents = []
    all_keywords = set()
    total_pages = 0
    total_nodes = 0
    total_images = 0

    for structure in structures:
        doc_info = {
            "file_name": structure.file_name,
            "title": structure.title,
            "pages": structure.total_pages,
            "nodes": structure.count_all_nodes(),
            "images": len(structure.images_index),
            "valid": structure.is_valid(),
            "coverage": structure.get_coverage_ratio(),
            "keywords": structure.get_all_keywords()[:10],
        }
        documents.append(doc_info)

        all_keywords.update(structure.get_all_keywords())
        total_pages += structure.total_pages
        total_nodes += structure.count_all_nodes()
        total_images += len(structure.images_index)

    index_data = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_documents": len(structures),
            "total_pages": total_pages,
            "total_nodes": total_nodes,
            "total_images": total_images,
            "valid_documents": len([d for d in documents if d["valid"]]),
        },
        "documents": documents,
        "all_keywords": sorted(list(all_keywords))[:100],
    }

    index_path.write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    logger.info(f"배치 인덱스 생성 완료: {index_path}")
    return index_path
