"""통합 LoRA용 SFT 데이터 생성기

3가지 소스에서 제품 간 관계 Q-A를 생성:
1. PDF 크로스 참조 추출 (자동)
2. 관계 테이블 + 템플릿 생성 (반자동)
3. 수동 시드 로드 (수동)

제품별 LoRA = 깊이(depth), 통합 LoRA = 관계(relations).
"""

import json
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import (
    CROSS_REFERENCE_PATTERNS,
    COMPONENT_SPLIT_DIRS,
    DIRECTORY_TO_PRODUCT,
    OTHER_PRODUCT_KEYWORDS,
    PDF_COMPONENT_TO_PRODUCT,
    PRODUCT_DISPLAY_NAMES,
    ProcessorConfig,
    UNIFIED_SYSTEM_PROMPTS,
)
from ..models.training import DataLanguage, UnifiedSFTRecord

logger = logging.getLogger(__name__)


# 관계 유형별 Q-A 템플릿
UNIFIED_QA_TEMPLATES: Dict[str, Dict[str, List[Tuple[str, str]]]] = {
    "R-01": {
        "ja": [
            ("{product_a}は{product_b}に依存していますか？",
             "はい。{description_ja}"),
            ("{product_a}を使用するために{product_b}は必要ですか？",
             "はい、{product_b}は必要です。{description_ja}"),
            ("{product_a}と{product_b}の依存関係を教えてください。",
             "{product_a}は{product_b}に依存しています。{description_ja}"),
        ],
        "ko": [
            ("{product_a}는 {product_b}에 의존합니까?",
             "네. {description_ko}"),
            ("{product_a}를 사용하려면 {product_b}가 필요합니까?",
             "네, {product_b}가 필요합니다. {description_ko}"),
            ("{product_a}와 {product_b}의 의존관계를 알려주세요.",
             "{product_a}는 {product_b}에 의존합니다. {description_ko}"),
        ],
    },
    "R-02": {
        "ja": [
            ("{product_a}と{product_b}の連携方法を教えてください。",
             "{description_ja}"),
            ("{product_a}から{product_b}にアクセスする方法は？",
             "{description_ja}"),
            ("{product_a}と{product_b}を連携させるための設定は？",
             "{description_ja}"),
            ("{product_a}で{product_b}を使用する手順を説明してください。",
             "{description_ja}"),
            ("{product_a}と{product_b}のインテグレーション方法は？",
             "{description_ja}"),
        ],
        "ko": [
            ("{product_a}와 {product_b}의 연동 방법을 알려주세요.",
             "{description_ko}"),
            ("{product_a}에서 {product_b}에 접근하는 방법은?",
             "{description_ko}"),
            ("{product_a}와 {product_b}를 연동하기 위한 설정은?",
             "{description_ko}"),
            ("{product_a}에서 {product_b}를 사용하는 절차를 설명해주세요.",
             "{description_ko}"),
            ("{product_a}와 {product_b}의 통합 방법은?",
             "{description_ko}"),
        ],
    },
    "R-03": {
        "ja": [
            ("{product_a}と{product_b}の違いは何ですか？",
             "{description_ja}"),
            ("{product_a}と{product_b}を比較してください。",
             "{description_ja}"),
            ("{product_a}と{product_b}はどう使い分けますか？",
             "{description_ja}"),
        ],
        "ko": [
            ("{product_a}와 {product_b}의 차이점은 무엇입니까?",
             "{description_ko}"),
            ("{product_a}와 {product_b}를 비교해주세요.",
             "{description_ko}"),
            ("{product_a}와 {product_b}는 어떻게 구분하여 사용합니까?",
             "{description_ko}"),
        ],
    },
    "R-05": {
        "ja": [
            ("{product_a}のエラーは{product_b}に影響しますか？",
             "{description_ja}"),
            ("{product_a}で障害が発生した場合、{product_b}への影響は？",
             "{description_ja}"),
        ],
        "ko": [
            ("{product_a}의 에러가 {product_b}에 영향을 줍니까?",
             "{description_ko}"),
            ("{product_a}에서 장애가 발생하면 {product_b}에 미치는 영향은?",
             "{description_ko}"),
        ],
    },
    "R-06": {
        "ja": [
            ("{host_name}のアプリケーションはOpenFrameに移行できますか？",
             "はい。{description_ja}"),
            ("{host_name}から{openframe_name}への移行方法は？",
             "{description_ja}"),
        ],
        "ko": [
            ("{host_name}의 애플리케이션을 OpenFrame으로 이행할 수 있습니까?",
             "네. {description_ko}"),
            ("{host_name}에서 {openframe_name}으로의 이행 방법은?",
             "{description_ko}"),
        ],
    },
    "R-07": {
        "ja": [
            ("{product_a}と{product_b}で共通の設定項目は何ですか？",
             "{description_ja}"),
            ("{product_a}と{product_b}の共通設定について教えてください。",
             "{description_ja}"),
        ],
        "ko": [
            ("{product_a}와 {product_b}에서 공통되는 설정 항목은 무엇입니까?",
             "{description_ko}"),
            ("{product_a}와 {product_b}의 공통 설정에 대해 알려주세요.",
             "{description_ko}"),
        ],
    },
    "R-08": {
        "ja": [
            ("{product_a}と{product_b}のプラットフォームの違いは何ですか？",
             "{description_ja}"),
            ("{product_a}と{product_b}の差異点を教えてください。",
             "{description_ja}"),
            ("{product_a}と{product_b}はどのように異なりますか？",
             "{description_ja}"),
        ],
        "ko": [
            ("{product_a}와 {product_b}의 플랫폼 차이는 무엇입니까?",
             "{description_ko}"),
            ("{product_a}와 {product_b}의 차이점을 알려주세요.",
             "{description_ko}"),
            ("{product_a}와 {product_b}는 어떻게 다릅니까?",
             "{description_ko}"),
        ],
    },
}


class UnifiedSFTGenerator:
    """통합 LoRA용 SFT 데이터 생성기"""

    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.data_dir = Path(__file__).parent.parent / "data"
        self.relations = self._load_relations()
        self.seeds = self._load_seeds()
        self.records: List[UnifiedSFTRecord] = []

    def _load_relations(self) -> dict:
        """product_relations.json 로드"""
        path = self.data_dir / "product_relations.json"
        if not path.exists():
            logger.warning(f"product_relations.json not found: {path}")
            return {"relations": [], "boot_sequence": {}, "migration_map": []}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_seeds(self) -> dict:
        """relation_seeds.json 로드"""
        path = self.data_dir / "relation_seeds.json"
        if not path.exists():
            logger.warning(f"relation_seeds.json not found: {path}")
            return {"seeds": []}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_all(self) -> List[UnifiedSFTRecord]:
        """전체 통합 SFT 데이터 생성"""
        logger.info("=== 통합 SFT 데이터 생성 시작 ===")

        # Source 1: PDF 크로스 참조 추출
        xref_records = self._extract_pdf_cross_references()
        logger.info(f"[Source 1] PDF 크로스참조: {len(xref_records)}건")

        # Source 2: 관계 테이블 기반 템플릿 생성
        template_records = self._generate_from_relation_table()
        logger.info(f"[Source 2] 관계 테이블 템플릿: {len(template_records)}건")

        # Source 3: 수동 시드 로드
        seed_records = self._load_seed_records()
        logger.info(f"[Source 3] 수동 시드: {len(seed_records)}건")

        # 통합 및 중복 제거
        all_records = xref_records + template_records + seed_records
        self.records = self._deduplicate(all_records)
        logger.info(f"중복 제거 후: {len(self.records)}건")

        # 밸런스 조정
        self.records = self._balance_by_relation_type(self.records)
        logger.info(f"밸런스 조정 후: {len(self.records)}건")

        self._log_stats()
        return self.records

    # ==========================================
    # Source 1: PDF 크로스 참조 추출
    # ==========================================

    def _extract_pdf_cross_references(self) -> List[UnifiedSFTRecord]:
        """PDF 내 다른 제품 언급 구간을 Q-A로 변환"""
        records = []

        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF not installed. Skipping PDF cross-reference extraction.")
            return records

        manuals_dir = self.config.manuals_dir
        if not manuals_dir.exists():
            logger.warning(f"Manuals directory not found: {manuals_dir}")
            return records

        for pdf_dir in sorted(manuals_dir.iterdir()):
            if not pdf_dir.is_dir():
                continue
            dir_name = pdf_dir.name

            for pdf_file in sorted(pdf_dir.glob("*.pdf")):
                product_id = self._get_product_id(dir_name, pdf_file.name)
                if not product_id:
                    continue

                try:
                    xrefs = self._extract_xrefs_from_pdf(pdf_file, product_id)
                    records.extend(xrefs)
                except Exception as e:
                    logger.debug(f"PDF 크로스참조 추출 실패: {pdf_file.name}: {e}")

        return records

    def _get_product_id(self, dir_name: str, pdf_name: str) -> Optional[str]:
        """디렉토리/PDF 파일명에서 제품 ID 결정"""
        if dir_name in COMPONENT_SPLIT_DIRS:
            # MVS/MSP/XSP 디렉토리: PDF 파일명으로 컴포넌트 구분
            match = re.match(r"OF_(\w+)_", pdf_name)
            if match:
                component = match.group(1)
                return PDF_COMPONENT_TO_PRODUCT.get(component)
        return DIRECTORY_TO_PRODUCT.get(dir_name)

    def _extract_xrefs_from_pdf(
        self, pdf_path: Path, source_product: str
    ) -> List[UnifiedSFTRecord]:
        """단일 PDF에서 크로스참조 추출"""
        import fitz

        records = []
        doc = fitz.open(str(pdf_path))

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if not text or len(text) < 50:
                continue

            # 다른 제품 키워드 감지
            for keyword, other_product in OTHER_PRODUCT_KEYWORDS.items():
                if other_product == source_product:
                    continue  # 자기 자신 제외

                # 키워드가 단어 경계에서 매칭되는지 확인
                pattern = rf"\b{re.escape(keyword)}\b"
                matches = list(re.finditer(pattern, text))
                if not matches:
                    continue

                for match in matches[:3]:  # 페이지당 최대 3건
                    # ±500자 컨텍스트 추출
                    start = max(0, match.start() - 250)
                    end = min(len(text), match.end() + 250)
                    context = text[start:end].strip()

                    if len(context) < 30:
                        continue

                    # 관계 유형 감지
                    relation_type = self._detect_relation_type(context)
                    if not relation_type:
                        relation_type = "R-02"  # 기본값: 연동

                    # Q-A 생성
                    record = self._context_to_qa(
                        context=context,
                        source_product=source_product,
                        other_product=other_product,
                        relation_type=relation_type,
                        source_file=pdf_path.name,
                        source_page=page_num + 1,
                    )
                    if record:
                        records.append(record)

        doc.close()
        return records

    def _detect_relation_type(self, context: str) -> Optional[str]:
        """컨텍스트에서 관계 유형 감지"""
        for rtype, pattern in CROSS_REFERENCE_PATTERNS.items():
            if re.search(pattern, context, re.IGNORECASE):
                return rtype
        return None

    def _context_to_qa(
        self,
        context: str,
        source_product: str,
        other_product: str,
        relation_type: str,
        source_file: str,
        source_page: int,
    ) -> Optional[UnifiedSFTRecord]:
        """크로스참조 컨텍스트를 Q-A로 변환"""
        source_name = PRODUCT_DISPLAY_NAMES.get(source_product, source_product)
        other_name = PRODUCT_DISPLAY_NAMES.get(other_product, other_product)

        # 일본어 기반 (PDF가 주로 일본어)
        instruction = f"{source_name}と{other_name}の関係について教えてください。"
        # 컨텍스트를 기반으로 응답 생성 (원문 인용)
        response = (
            f"{source_name}と{other_name}の関係:\n\n"
            f"{context}\n\n"
            f"（出典: {source_file}, p.{source_page}）"
        )

        if len(response) < 50:
            return None

        return UnifiedSFTRecord(
            instruction=instruction,
            response=response,
            system_prompt=UNIFIED_SYSTEM_PROMPTS["ja"],
            products_involved=[source_product, other_product],
            relation_type=relation_type,
            language=DataLanguage.JA,
            source="pdf_xref",
            source_file=source_file,
            source_page=source_page,
        )

    # ==========================================
    # Source 2: 관계 테이블 기반 템플릿 생성
    # ==========================================

    def _generate_from_relation_table(self) -> List[UnifiedSFTRecord]:
        """관계 테이블에서 Q-A 템플릿으로 레코드 생성"""
        records = []

        # 일반 관계 (R-01 ~ R-08)
        for rel in self.relations.get("relations", []):
            if "type" not in rel:
                continue  # skip _comment separators
            rel_type = rel["type"]
            templates = UNIFIED_QA_TEMPLATES.get(rel_type, {})

            product_a_name = PRODUCT_DISPLAY_NAMES.get(
                rel["product_a"], rel["product_a"]
            )
            product_b_name = PRODUCT_DISPLAY_NAMES.get(
                rel["product_b"], rel["product_b"]
            )

            for lang in ["ja", "ko"]:
                lang_templates = templates.get(lang, [])
                desc_key = f"description_{lang}"
                description = rel.get(desc_key, "")

                for q_template, a_template in lang_templates:
                    # R-06 templates use host_name/openframe_name
                    fmt_kwargs = {
                        "product_a": product_a_name,
                        "product_b": product_b_name,
                        "host_name": product_a_name,
                        "openframe_name": product_b_name,
                        "description_ja": rel.get("description_ja", ""),
                        "description_ko": rel.get("description_ko", ""),
                    }
                    instruction = q_template.format(**fmt_kwargs)
                    response = a_template.format(**fmt_kwargs)

                    records.append(
                        UnifiedSFTRecord(
                            instruction=instruction,
                            response=response,
                            system_prompt=UNIFIED_SYSTEM_PROMPTS[lang],
                            products_involved=[rel["product_a"], rel["product_b"]],
                            relation_type=rel_type,
                            language=DataLanguage(lang),
                            source="relation_table",
                        )
                    )

        # 마이그레이션 관계 (R-06)
        r06_templates = UNIFIED_QA_TEMPLATES.get("R-06", {})
        for mig in self.relations.get("migration_map", []):
            host_name = mig["host"]
            of_product = mig["openframe"]
            of_name = PRODUCT_DISPLAY_NAMES.get(of_product, of_product)

            for lang in ["ja", "ko"]:
                lang_templates = r06_templates.get(lang, [])
                desc_key = f"description_{lang}"
                description = mig.get(desc_key, "")

                for q_template, a_template in lang_templates:
                    instruction = q_template.format(
                        host_name=host_name,
                        openframe_name=of_name,
                    )
                    response = a_template.format(
                        host_name=host_name,
                        openframe_name=of_name,
                        description_ja=mig.get("description_ja", ""),
                        description_ko=mig.get("description_ko", ""),
                    )

                    records.append(
                        UnifiedSFTRecord(
                            instruction=instruction,
                            response=response,
                            system_prompt=UNIFIED_SYSTEM_PROMPTS[lang],
                            products_involved=[of_product],
                            relation_type="R-06",
                            language=DataLanguage(lang),
                            source="relation_table",
                        )
                    )

        # 기동 순서 관계 (R-04) - boot_sequence에서 생성
        boot_seq = self.relations.get("boot_sequence", {})
        r04_order = boot_seq.get("order", [])
        if r04_order:
            records.extend(self._generate_boot_sequence_qa(r04_order))

        mw_boot = boot_seq.get("middleware_boot", [])
        if mw_boot:
            records.extend(self._generate_boot_sequence_qa(mw_boot, prefix="ミドルウェア"))

        # 플랫폼 차이 (platform_differences)
        platform_diffs = self.relations.get("platform_differences", {})
        if platform_diffs:
            records.extend(self._generate_platform_diff_qa(platform_diffs))

        return records

    def _generate_boot_sequence_qa(
        self, order: List[dict], prefix: str = "OpenFrame"
    ) -> List[UnifiedSFTRecord]:
        """기동 순서에서 Q-A 생성"""
        records = []
        products = [step["product"] for step in order]

        for lang_code in ["ja", "ko"]:
            lang = DataLanguage(lang_code)
            desc_key = f"description_{lang_code}"

            # 전체 기동 순서
            boot_lines = []
            for step in order:
                name = PRODUCT_DISPLAY_NAMES.get(step["product"], step["product"])
                desc = step.get(desc_key, step.get("description_ja", ""))
                boot_lines.append(f"{step['step']}. {name} ({step['command']}) - {desc}")
            boot_text = "\n".join(boot_lines)

            shutdown_lines = list(reversed(boot_lines))
            for i, line in enumerate(shutdown_lines):
                shutdown_lines[i] = re.sub(r"^\d+\.", f"{i + 1}.", line)
            shutdown_text = "\n".join(shutdown_lines)

            if lang_code == "ja":
                records.append(
                    UnifiedSFTRecord(
                        instruction=f"{prefix}全体の起動順序を教えてください。",
                        response=f"{prefix}の推奨起動順序:\n\n{boot_text}",
                        system_prompt=UNIFIED_SYSTEM_PROMPTS["ja"],
                        products_involved=products,
                        relation_type="R-04",
                        language=lang,
                        source="relation_table",
                    )
                )
                records.append(
                    UnifiedSFTRecord(
                        instruction=f"{prefix}全体の停止順序を教えてください。",
                        response=f"{prefix}の停止は起動の逆順で行います:\n\n{shutdown_text}",
                        system_prompt=UNIFIED_SYSTEM_PROMPTS["ja"],
                        products_involved=products,
                        relation_type="R-04",
                        language=lang,
                        source="relation_table",
                    )
                )
            else:
                records.append(
                    UnifiedSFTRecord(
                        instruction=f"{prefix} 전체의 기동 순서를 알려주세요.",
                        response=f"{prefix}의 권장 기동 순서:\n\n{boot_text}",
                        system_prompt=UNIFIED_SYSTEM_PROMPTS["ko"],
                        products_involved=products,
                        relation_type="R-04",
                        language=lang,
                        source="relation_table",
                    )
                )
                records.append(
                    UnifiedSFTRecord(
                        instruction=f"{prefix} 전체의 정지 순서를 알려주세요.",
                        response=f"{prefix}의 정지는 기동의 역순으로 수행합니다:\n\n{shutdown_text}",
                        system_prompt=UNIFIED_SYSTEM_PROMPTS["ko"],
                        products_involved=products,
                        relation_type="R-04",
                        language=lang,
                        source="relation_table",
                    )
                )

        return records

    def _generate_platform_diff_qa(
        self, platform_diffs: dict
    ) -> List[UnifiedSFTRecord]:
        """platform_differences 섹션에서 Q-A 생성"""
        records = []
        categories = platform_diffs.get("categories", [])

        for cat in categories:
            category = cat.get("category", "")
            mvs = cat.get("mvs", "")
            msp = cat.get("msp", "")
            xsp = cat.get("xsp", "")

            # 일본어
            ja_diff = cat.get("key_differences_ja", "")
            ja_detail = self._format_platform_detail(category, mvs, msp, xsp, "ja")
            ja_response = f"{ja_detail}\n\n{ja_diff}" if ja_diff else ja_detail

            records.append(
                UnifiedSFTRecord(
                    instruction=f"MVS、MSP、XSPの{category}の違いを教えてください。",
                    response=ja_response,
                    system_prompt=UNIFIED_SYSTEM_PROMPTS["ja"],
                    products_involved=["openframe_base_v2"],
                    relation_type="R-08",
                    language=DataLanguage.JA,
                    source="relation_table",
                )
            )

            # 한국어
            ko_diff = cat.get("key_differences_ko", "")
            ko_detail = self._format_platform_detail(category, mvs, msp, xsp, "ko")
            ko_response = f"{ko_detail}\n\n{ko_diff}" if ko_diff else ko_detail

            records.append(
                UnifiedSFTRecord(
                    instruction=f"MVS, MSP, XSP의 {category} 차이를 알려주세요.",
                    response=ko_response,
                    system_prompt=UNIFIED_SYSTEM_PROMPTS["ko"],
                    products_involved=["openframe_base_v2"],
                    relation_type="R-08",
                    language=DataLanguage.KO,
                    source="relation_table",
                )
            )

        return records

    def _format_platform_detail(
        self, category: str, mvs: str, msp: str, xsp: str, lang: str
    ) -> str:
        """플랫폼 비교 상세 포맷"""
        if lang == "ja":
            return (
                f"【{category}のプラットフォーム比較】\n"
                f"- MVS: {mvs}\n"
                f"- MSP: {msp}\n"
                f"- XSP: {xsp}"
            )
        else:
            return (
                f"【{category}의 플랫폼 비교】\n"
                f"- MVS: {mvs}\n"
                f"- MSP: {msp}\n"
                f"- XSP: {xsp}"
            )

    # ==========================================
    # Source 3: 수동 시드 로드
    # ==========================================

    def _load_seed_records(self) -> List[UnifiedSFTRecord]:
        """수동 시드 Q-A를 레코드로 변환"""
        records = []

        for seed in self.seeds.get("seeds", []):
            rel_type = seed.get("relation_type", "R-01")
            products = seed.get("products_involved", [])

            # 일본어 시드
            if seed.get("instruction_ja") and seed.get("response_ja"):
                records.append(
                    UnifiedSFTRecord(
                        instruction=seed["instruction_ja"],
                        response=seed["response_ja"],
                        system_prompt=UNIFIED_SYSTEM_PROMPTS["ja"],
                        products_involved=products,
                        relation_type=rel_type,
                        language=DataLanguage.JA,
                        source="seed",
                    )
                )

            # 한국어 시드
            if seed.get("instruction_ko") and seed.get("response_ko"):
                records.append(
                    UnifiedSFTRecord(
                        instruction=seed["instruction_ko"],
                        response=seed["response_ko"],
                        system_prompt=UNIFIED_SYSTEM_PROMPTS["ko"],
                        products_involved=products,
                        relation_type=rel_type,
                        language=DataLanguage.KO,
                        source="seed",
                    )
                )

        return records

    # ==========================================
    # 중복 제거 + 밸런스 조정
    # ==========================================

    def _deduplicate(self, records: List[UnifiedSFTRecord]) -> List[UnifiedSFTRecord]:
        """중복 제거 (우선순위: seed > relation_table > pdf_xref)"""
        SOURCE_PRIORITY = {"seed": 0, "relation_table": 1, "pdf_xref": 2}

        # 우선순위 순으로 정렬
        records.sort(key=lambda r: SOURCE_PRIORITY.get(r.source, 99))

        seen_keys = set()
        unique = []

        for record in records:
            # 키: (products tuple, relation_type, language, instruction 처음 50자)
            products_key = tuple(sorted(record.products_involved))
            instruction_key = record.instruction[:50]
            key = (products_key, record.relation_type, record.language.value, instruction_key)

            if key not in seen_keys:
                seen_keys.add(key)
                # 저품질 필터: 응답 30자 미만 제거
                if len(record.response) >= 30:
                    unique.append(record)

        return unique

    def _balance_by_relation_type(
        self, records: List[UnifiedSFTRecord]
    ) -> List[UnifiedSFTRecord]:
        """관계 유형별 밸런스 조정 (최대/최소 비율 2배 이내)"""
        by_type = defaultdict(list)
        for r in records:
            by_type[r.relation_type].append(r)

        if not by_type:
            return records

        counts = {t: len(recs) for t, recs in by_type.items()}
        max_count = max(counts.values())
        min_count = min(counts.values())

        # 비율 2배 이내이면 조정 불필요
        if min_count > 0 and max_count / min_count <= 2.0:
            return records

        # 최대 카운트의 2배까지만 허용 (초과분 트림)
        target_max = min_count * 2 if min_count > 0 else max_count
        balanced = []
        for rtype, recs in by_type.items():
            if len(recs) > target_max:
                # seed와 relation_table 우선 유지
                recs.sort(key=lambda r: {"seed": 0, "relation_table": 1, "pdf_xref": 2}.get(r.source, 2))
                balanced.extend(recs[:target_max])
                logger.info(f"  {rtype}: {len(recs)} → {target_max} (트림)")
            else:
                balanced.extend(recs)

        return balanced

    # ==========================================
    # 통계 로깅
    # ==========================================

    def _log_stats(self):
        """생성 통계 출력"""
        logger.info("=== 통합 SFT 생성 통계 ===")
        logger.info(f"총 레코드: {len(self.records)}건")

        # 소스별
        source_counts = Counter(r.source for r in self.records)
        for source, count in source_counts.most_common():
            logger.info(f"  소스 {source}: {count}건")

        # 관계 유형별
        type_counts = Counter(r.relation_type for r in self.records)
        for rtype, count in sorted(type_counts.items()):
            logger.info(f"  {rtype}: {count}건")

        # 언어별
        lang_counts = Counter(r.language.value for r in self.records)
        for lang, count in lang_counts.most_common():
            logger.info(f"  {lang}: {count}건")
