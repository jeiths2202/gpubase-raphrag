#!/usr/bin/env python3
"""
QLoRA Format Converter

학습 데이터셋(learning_dataset.json)을 QLoRA Trainer 호환 형식으로 변환합니다.
Qwen2.5 ChatML 형식으로 출력하여 qlora_trainer.py와 호환됩니다.

Usage:
    python convert_to_qlora.py --input learning_dataset.json --output /opt/kms/data/training/
    python convert_to_qlora.py --input learning_dataset.json --output ./output --augment
    python convert_to_qlora.py --input learning_dataset.json --output ./output --train-ratio 0.9
"""
import os
import sys
import json
import re
import random
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ConversionStats:
    """변환 통계"""
    total: int = 0
    converted: int = 0
    skipped: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_language: Dict[str, int] = field(default_factory=dict)
    by_product: Dict[str, int] = field(default_factory=dict)
    augmented: int = 0
    train_count: int = 0
    eval_count: int = 0


# ============================================
# Multi-LoRA v2 제품 매핑 (vllm_adapter.py와 동기화)
# ============================================
# 24개 QLoRA v2 어댑터가 GPU 5, 6, 7에 분산 배포됨
MULTI_LORA_PRODUCTS = {
    # GPU 5 - 대형 제품 8개
    "tibero7_v2": {
        "aliases": ["Tibero", "tibero", "TIBERO"],
        "min_samples": 100,
    },
    "jeus_v2": {
        "aliases": ["JEUS", "jeus", "Jeus"],
        "min_samples": 100,
    },
    "tmax_v2": {
        "aliases": ["Tmax", "tmax", "TMAX"],
        "min_samples": 100,
    },
    "openframe_common_v2": {
        "aliases": ["OF_Common", "OF_Common_MVS", "OF_Common_MSP", "OF_Common_XSP", "OpenFrame_Common"],
        "min_samples": 50,
    },
    "openframe_batch_v2": {
        "aliases": ["OF_Batch", "OF_Batch_MVS", "OF_Batch_MSP", "OF_Batch_XSP", "OF_Batch_VOS3", "OpenFrame_Batch"],
        "min_samples": 50,
    },
    "webtob_v2": {
        "aliases": ["WebtoB", "webtob", "WEBTOB"],
        "min_samples": 50,
    },
    "openframe_vos3_v2": {
        "aliases": ["OF_VOS3", "VOS3", "vos3"],
        "min_samples": 30,
    },
    "openframe_osc_v2": {
        "aliases": ["OF_OSC", "OF_OSC_MVS", "OF_OSC_MSP", "OSC", "osc"],
        "min_samples": 30,
    },
    # GPU 6 - 중형 제품 8개
    "openframe_base_v2": {
        "aliases": ["OF_Base", "OpenFrame_Base", "Base"],
        "min_samples": 30,
    },
    "ofmanager_v2": {
        "aliases": ["OFManager", "ofmanager", "Manager"],
        "min_samples": 30,
    },
    "openframe_aim_v2": {
        "aliases": ["OF_AIM", "OF_AIM_MSP", "OF_AIM_XSP", "AIM", "aim"],
        "min_samples": 20,
    },
    "protrieve_v2": {
        "aliases": ["ProTrieve", "protrieve", "PROTRIEVE"],
        "min_samples": 20,
    },
    "openframe_osi_v2": {
        "aliases": ["OF_OSI", "OF_OSI_MVS", "OSI", "osi"],
        "min_samples": 20,
    },
    "openframe_tacf_v2": {
        "aliases": ["OF_TACF", "OF_TACF_MVS", "OF_TACF_MSP", "OF_TACF_XSP", "TACF", "tacf"],
        "min_samples": 20,
    },
    "openframe_gateway_v2": {
        "aliases": ["OF_Gateway", "OF_GW", "Gateway", "gateway"],
        "min_samples": 20,
    },
    "ofpli_v2": {
        "aliases": ["OFPLI", "ofpli", "PLI", "pli"],
        "min_samples": 10,
    },
    # GPU 7 - 소형 제품 8개
    "ofcobol_v2": {
        "aliases": ["OFCOBOL", "ofcobol", "COBOL", "cobol"],
        "min_samples": 10,
    },
    "prosync_v2": {
        "aliases": ["ProSync", "prosync", "PROSYNC"],
        "min_samples": 10,
    },
    "openframe_ndb_v2": {
        "aliases": ["OF_NDB", "NDB", "ndb"],
        "min_samples": 10,
    },
    "ofstudio_v2": {
        "aliases": ["OFStudio", "ofstudio", "Studio"],
        "min_samples": 10,
    },
    "ofminer_v2": {
        "aliases": ["OFMiner", "ofminer", "Miner"],
        "min_samples": 10,
    },
    "prosort_v2": {
        "aliases": ["ProSort", "prosort", "PROSORT"],
        "min_samples": 10,
    },
    "openframe_hidb_v2": {
        "aliases": ["OF_HiDB", "OF_HiDB_MVS", "HiDB", "hidb"],
        "min_samples": 10,
    },
    "ofasm_v2": {
        "aliases": ["OFAsm", "ofasm", "ASM", "asm"],
        "min_samples": 10,
    },
}

# ============================================
# 제품별 시스템 프롬프트 (Multi-LoRA 전문 어시스턴트)
# ============================================
PRODUCT_SYSTEM_PROMPTS = {
    "jeus_v2": {
        "ja": "あなたはJEUS専門のテクニカルアシスタントです。JEUSに関する質問に正確に回答してください。",
        "ko": "당신은 JEUS 전문 기술 어시스턴트입니다. JEUS에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a JEUS technical expert assistant. Answer questions about JEUS accurately."
    },
    "tibero7_v2": {
        "ja": "あなたはTibero専門のテクニカルアシスタントです。Tiberoに関する質問に正確に回答してください。",
        "ko": "당신은 Tibero 전문 기술 어시스턴트입니다. Tibero에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a Tibero technical expert assistant. Answer questions about Tibero accurately."
    },
    "tmax_v2": {
        "ja": "あなたはTmax専門のテクニカルアシスタントです。Tmaxに関する質問に正確に回答してください。",
        "ko": "당신은 Tmax 전문 기술 어시스턴트입니다. Tmax에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a Tmax technical expert assistant. Answer questions about Tmax accurately."
    },
    "webtob_v2": {
        "ja": "あなたはWebtoB専門のテクニカルアシスタントです。WebtoBに関する質問に正確に回答してください。",
        "ko": "당신은 WebtoB 전문 기술 어시스턴트입니다. WebtoB에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a WebtoB technical expert assistant. Answer questions about WebtoB accurately."
    },
    "openframe_common_v2": {
        "ja": "あなたはOpenFrame共通機能専門のテクニカルアシスタントです。OpenFrameに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame 공통 기능 전문 기술 어시스턴트입니다. OpenFrame에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame Common technical expert assistant. Answer questions about OpenFrame accurately."
    },
    "openframe_batch_v2": {
        "ja": "あなたはOpenFrame Batch専門のテクニカルアシスタントです。バッチ処理に関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame Batch 전문 기술 어시스턴트입니다. 배치 처리에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame Batch technical expert assistant. Answer questions about batch processing accurately."
    },
    "openframe_osc_v2": {
        "ja": "あなたはOpenFrame OSC専門のテクニカルアシスタントです。OSCに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame OSC 전문 기술 어시스턴트입니다. OSC에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame OSC technical expert assistant. Answer questions about OSC accurately."
    },
    "openframe_vos3_v2": {
        "ja": "あなたはOpenFrame VOS3専門のテクニカルアシスタントです。VOS3に関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame VOS3 전문 기술 어시스턴트입니다. VOS3에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame VOS3 technical expert assistant. Answer questions about VOS3 accurately."
    },
    "openframe_base_v2": {
        "ja": "あなたはOpenFrame Base専門のテクニカルアシスタントです。OpenFrame Baseに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame Base 전문 기술 어시스턴트입니다. OpenFrame Base에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame Base technical expert assistant. Answer questions about OpenFrame Base accurately."
    },
    "ofmanager_v2": {
        "ja": "あなたはOFManager専門のテクニカルアシスタントです。OFManagerに関する質問に正確に回答してください。",
        "ko": "당신은 OFManager 전문 기술 어시스턴트입니다. OFManager에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OFManager technical expert assistant. Answer questions about OFManager accurately."
    },
    "openframe_aim_v2": {
        "ja": "あなたはOpenFrame AIM専門のテクニカルアシスタントです。AIMに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame AIM 전문 기술 어시스턴트입니다. AIM에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame AIM technical expert assistant. Answer questions about AIM accurately."
    },
    "openframe_osi_v2": {
        "ja": "あなたはOpenFrame OSI専門のテクニカルアシスタントです。OSIに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame OSI 전문 기술 어시스턴트입니다. OSI에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame OSI technical expert assistant. Answer questions about OSI accurately."
    },
    "openframe_tacf_v2": {
        "ja": "あなたはOpenFrame TACF専門のテクニカルアシスタントです。TACFに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame TACF 전문 기술 어시스턴트입니다. TACF에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame TACF technical expert assistant. Answer questions about TACF accurately."
    },
    "openframe_gateway_v2": {
        "ja": "あなたはOpenFrame Gateway専門のテクニカルアシスタントです。Gatewayに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame Gateway 전문 기술 어시스턴트입니다. Gateway에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame Gateway technical expert assistant. Answer questions about Gateway accurately."
    },
    "openframe_ndb_v2": {
        "ja": "あなたはOpenFrame NDB専門のテクニカルアシスタントです。NDBに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame NDB 전문 기술 어시스턴트입니다. NDB에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame NDB technical expert assistant. Answer questions about NDB accurately."
    },
    "openframe_hidb_v2": {
        "ja": "あなたはOpenFrame HiDB専門のテクニカルアシスタントです。HiDBに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame HiDB 전문 기술 어시스턴트입니다. HiDB에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame HiDB technical expert assistant. Answer questions about HiDB accurately."
    },
    "protrieve_v2": {
        "ja": "あなたはProTrieve専門のテクニカルアシスタントです。ProTrieveに関する質問に正確に回答してください。",
        "ko": "당신은 ProTrieve 전문 기술 어시스턴트입니다. ProTrieve에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a ProTrieve technical expert assistant. Answer questions about ProTrieve accurately."
    },
    "prosync_v2": {
        "ja": "あなたはProSync専門のテクニカルアシスタントです。ProSyncに関する質問に正確に回答してください。",
        "ko": "당신은 ProSync 전문 기술 어시스턴트입니다. ProSync에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a ProSync technical expert assistant. Answer questions about ProSync accurately."
    },
    "prosort_v2": {
        "ja": "あなたはProSort専門のテクニカルアシスタントです。ProSortに関する質問に正確に回答してください。",
        "ko": "당신은 ProSort 전문 기술 어시스턴트입니다. ProSort에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a ProSort technical expert assistant. Answer questions about ProSort accurately."
    },
    "ofpli_v2": {
        "ja": "あなたはOFPLI専門のテクニカルアシスタントです。OFPLIに関する質問に正確に回答してください。",
        "ko": "당신은 OFPLI 전문 기술 어시스턴트입니다. OFPLI에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OFPLI technical expert assistant. Answer questions about OFPLI accurately."
    },
    "ofcobol_v2": {
        "ja": "あなたはOFCOBOL専門のテクニカルアシスタントです。OFCOBOLに関する質問に正確に回答してください。",
        "ko": "당신은 OFCOBOL 전문 기술 어시스턴트입니다. OFCOBOL에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OFCOBOL technical expert assistant. Answer questions about OFCOBOL accurately."
    },
    "ofasm_v2": {
        "ja": "あなたはOFASM専門のテクニカルアシスタントです。OFASMに関する質問に正確に回答してください。",
        "ko": "당신은 OFASM 전문 기술 어시스턴트입니다. OFASM에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OFASM technical expert assistant. Answer questions about OFASM accurately."
    },
    "ofstudio_v2": {
        "ja": "あなたはOFStudio専門のテクニカルアシスタントです。OFStudioに関する質問に正確に回答してください。",
        "ko": "당신은 OFStudio 전문 기술 어시스턴트입니다. OFStudio에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OFStudio technical expert assistant. Answer questions about OFStudio accurately."
    },
    "ofminer_v2": {
        "ja": "あなたはOFMiner専門のテクニカルアシスタントです。OFMinerに関する質問に正確に回答してください。",
        "ko": "당신은 OFMiner 전문 기술 어시스턴트입니다. OFMiner에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OFMiner technical expert assistant. Answer questions about OFMiner accurately."
    },
}


def get_product_system_prompt(product: str, lang: str) -> str:
    """제품별 시스템 프롬프트 반환"""
    if product in PRODUCT_SYSTEM_PROMPTS:
        prompts = PRODUCT_SYSTEM_PROMPTS[product]
        return prompts.get(lang, prompts.get("ja", ""))
    # 기본 프롬프트
    default_prompts = {
        "ja": "あなたはOpenFrame技術専門のアシスタントです。技術的な質問に正確に回答してください。",
        "ko": "당신은 OpenFrame 기술 전문 어시스턴트입니다. 기술적인 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame technical expert assistant. Answer technical questions accurately."
    }
    return default_prompts.get(lang, default_prompts["ja"])


def infer_product_from_source(source_file: str) -> Optional[str]:
    """source_file 경로에서 제품명 추론"""
    if not source_file:
        return None

    source_upper = source_file.upper()

    # 파일명 패턴으로 제품 추론
    product_patterns = {
        "jeus_v2": ["JEUS"],
        "tibero7_v2": ["TIBERO"],
        "tmax_v2": ["TMAX_"],  # TMAX_ 로 구분 (TMAX만으로는 다른 제품과 혼동)
        "webtob_v2": ["WEBTOB"],
        "openframe_common_v2": ["OF_COMMON", "OPENFRAME_COMMON"],
        "openframe_batch_v2": ["OF_BATCH", "OPENFRAME_BATCH"],
        "openframe_vos3_v2": ["OF_VOS3", "OPENFRAME_VOS3", "VOS3"],
        "openframe_osc_v2": ["OF_OSC", "OPENFRAME_OSC"],
        "openframe_base_v2": ["OF_BASE", "OPENFRAME_BASE"],
        "ofmanager_v2": ["OFMANAGER", "OF_MANAGER"],
        "openframe_aim_v2": ["OF_AIM", "OPENFRAME_AIM"],
        "protrieve_v2": ["PROTRIEVE"],
        "openframe_osi_v2": ["OF_OSI", "OPENFRAME_OSI"],
        "openframe_tacf_v2": ["OF_TACF", "OPENFRAME_TACF"],
        "openframe_gateway_v2": ["OF_GATEWAY", "OPENFRAME_GATEWAY"],
        "ofpli_v2": ["OFPLI", "OF_PLI"],
        "ofcobol_v2": ["OFCOBOL", "OF_COBOL"],
        "prosync_v2": ["PROSYNC"],
        "openframe_ndb_v2": ["OF_NDB", "OPENFRAME_NDB"],
        "ofstudio_v2": ["OFSTUDIO", "OF_STUDIO"],
        "ofminer_v2": ["OFMINER", "OF_MINER"],
        "prosort_v2": ["PROSORT"],
        "openframe_hidb_v2": ["OF_HIDB", "OPENFRAME_HIDB"],
        "ofasm_v2": ["OFASM", "OF_ASM"],
    }

    for adapter_name, patterns in product_patterns.items():
        for pattern in patterns:
            if pattern in source_upper:
                return adapter_name

    return None


def normalize_product_name(product: str, source_file: str = None) -> str:
    """제품명을 Multi-LoRA v2 어댑터 이름으로 정규화

    Args:
        product: 원본 product 필드 값
        source_file: source_file 경로 (Unknown일 때 fallback으로 사용)
    """
    # 1차: 정상적인 product 매핑
    if product and product != "Unknown":
        for adapter_name, config in MULTI_LORA_PRODUCTS.items():
            if product in config["aliases"] or product.lower() == adapter_name.replace("_v2", "").replace("_", ""):
                return adapter_name

    # 2차: product가 Unknown이면 source_file에서 추론
    if (not product or product == "Unknown") and source_file:
        inferred = infer_product_from_source(source_file)
        if inferred:
            return inferred

    # 매핑되지 않은 제품은 unknown으로
    return "unknown"


class QuestionTemplates:
    """타입별/언어별 질문 템플릿 관리"""

    def __init__(self, templates_path: str):
        with open(templates_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.templates = data.get("templates", {})
        self.system_prompts = data.get("system_prompts", {})
        self.default_type = data.get("default_type", "concept")
        self.default_language = data.get("default_language", "ja")

    def get_template(self, item_type: str, lang: str, index: int = 0) -> str:
        """특정 타입/언어의 질문 템플릿 반환"""
        type_templates = self.templates.get(item_type, self.templates.get(self.default_type, {}))
        lang_templates = type_templates.get(lang, type_templates.get(self.default_language, []))

        if not lang_templates:
            return "{name}について説明してください。"

        return lang_templates[index % len(lang_templates)]

    def get_all_templates(self, item_type: str, lang: str) -> List[str]:
        """데이터 증강용 모든 템플릿 반환"""
        type_templates = self.templates.get(item_type, self.templates.get(self.default_type, {}))
        return type_templates.get(lang, type_templates.get(self.default_language, []))

    def get_system_prompt(self, lang: str) -> str:
        """시스템 프롬프트 반환"""
        return self.system_prompts.get(lang, self.system_prompts.get(self.default_language, ""))


class QLoRAConverter:
    """학습 데이터셋을 QLoRA 형식으로 변환"""

    def __init__(self, templates_path: str):
        self.templates = QuestionTemplates(templates_path)
        self.stats = ConversionStats()

    def detect_language(self, text: str) -> str:
        """텍스트에서 주요 언어 감지"""
        if not text:
            return "ja"

        # 한글 범위: AC00-D7AF (완성형), 1100-11FF (자모)
        korean_pattern = r'[\uAC00-\uD7AF\u1100-\u11FF]'
        # 히라가나: 3040-309F, 가타카나: 30A0-30FF
        japanese_pattern = r'[\u3040-\u309F\u30A0-\u30FF]'

        korean_count = len(re.findall(korean_pattern, text))
        japanese_count = len(re.findall(japanese_pattern, text))

        # 한글이 더 많으면 한국어
        if korean_count > japanese_count and korean_count > 10:
            return "ko"
        # 일본어 문자가 있으면 일본어
        elif japanese_count > 0:
            return "ja"
        # 기본값 영어
        else:
            return "en"

    def format_output(self, item: Dict[str, Any]) -> str:
        """구조화된 답변 포맷팅"""
        parts = []

        # 메인 설명
        description = item.get("description", "")
        if description:
            parts.append(description)

        # 구문 (command, api인 경우)
        syntax = item.get("syntax")
        if syntax:
            parts.append(f"\n\n**構文/Syntax**:\n```\n{syntax}\n```")

        # 파라미터
        parameters = item.get("parameters", [])
        if parameters and len(parameters) > 0:
            params_text = "\n".join([f"- {p}" for p in parameters if p])
            if params_text:
                parts.append(f"\n\n**パラメータ/Parameters**:\n{params_text}")

        # 예시
        examples = item.get("examples", [])
        if examples and len(examples) > 0:
            examples_text = "\n".join([f"```\n{e}\n```" for e in examples if e])
            if examples_text:
                parts.append(f"\n\n**例/Example**:\n{examples_text}")

        # 관련 항목
        related = item.get("related", [])
        if related and len(related) > 0:
            related_text = ", ".join([r for r in related if r])
            if related_text:
                parts.append(f"\n\n**関連/Related**: {related_text}")

        # 제품 정보 (중요: 할루시네이션 방지)
        product = item.get("product", "")
        if product and product != "Unknown":
            parts.append(f"\n\n**製品/Product**: {product}")

        # 소스 정보
        source_file = item.get("source_file", "")
        if source_file and source_file not in ["keyword_only", "manager_definition", "summary"]:
            parts.append(f"\n\n**出典/Source**: {source_file}")

        return "".join(parts)

    def to_chatml(self, instruction: str, output: str, lang: str, product: str = None) -> Dict[str, str]:
        """Qwen2.5 ChatML 형식으로 변환

        Args:
            instruction: 사용자 질문
            output: 어시스턴트 답변
            lang: 언어 (ja, ko, en)
            product: 제품명 (Multi-LoRA용, 예: jeus_v2)
        """
        # 제품별 시스템 프롬프트 사용
        if product:
            system_prompt = get_product_system_prompt(product, lang)
        else:
            system_prompt = self.templates.get_system_prompt(lang)

        text = f"""<|im_start|>system
{system_prompt}<|im_end|>
<|im_start|>user
{instruction}<|im_end|>
<|im_start|>assistant
{output}<|im_end|>"""

        return {"text": text}

    def convert_item(self, item: Dict[str, Any], template_index: int = 0, product: str = None) -> Optional[Dict[str, str]]:
        """단일 항목 변환

        Args:
            item: 변환할 데이터 항목
            template_index: 질문 템플릿 인덱스 (데이터 증강용)
            product: 제품명 (Multi-LoRA용, 예: jeus_v2)
        """
        name = item.get("name", "")
        item_type = item.get("type", "concept")
        description = item.get("description", "")

        if not name or not description:
            return None

        # 언어 감지
        lang = self.detect_language(description)

        # 질문 템플릿 적용
        template = self.templates.get_template(item_type, lang, template_index)
        instruction = template.format(name=name)

        # 답변 포맷팅
        output = self.format_output(item)

        # ChatML 형식 변환 (제품별 시스템 프롬프트 적용)
        return self.to_chatml(instruction, output, lang, product)

    def convert(
        self,
        input_path: str,
        output_dir: str,
        train_ratio: float = 0.8,
        augment: bool = False,
        seed: int = 42
    ) -> ConversionStats:
        """메인 변환 로직"""
        random.seed(seed)

        # 입력 파일 로드
        logger.info(f"Loading input file: {input_path}")
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        items = data if isinstance(data, list) else data.get("items", [])
        self.stats.total = len(items)
        logger.info(f"Loaded {self.stats.total} items")

        # 변환
        converted_items = []
        for item in items:
            item_type = item.get("type", "concept")
            raw_product = item.get("product", "Unknown")
            source_file = item.get("source_file", "")
            normalized_product = normalize_product_name(raw_product, source_file)
            description = item.get("description", "")
            lang = self.detect_language(description)

            # 기본 변환 (첫 번째 템플릿, 제품별 시스템 프롬프트 적용)
            result = self.convert_item(item, 0, product=normalized_product)
            if result:
                converted_items.append(result)
                self.stats.converted += 1

                # 통계 업데이트
                self.stats.by_type[item_type] = self.stats.by_type.get(item_type, 0) + 1
                self.stats.by_language[lang] = self.stats.by_language.get(lang, 0) + 1
                self.stats.by_product[raw_product] = self.stats.by_product.get(raw_product, 0) + 1

                # 데이터 증강 (추가 템플릿 적용)
                if augment:
                    templates = self.templates.get_all_templates(item_type, lang)
                    for i in range(1, len(templates)):
                        aug_result = self.convert_item(item, i, product=normalized_product)
                        if aug_result:
                            converted_items.append(aug_result)
                            self.stats.augmented += 1
            else:
                self.stats.skipped += 1

        logger.info(f"Converted: {self.stats.converted}, Skipped: {self.stats.skipped}, Augmented: {self.stats.augmented}")

        # 셔플 및 분할
        random.shuffle(converted_items)
        split_idx = int(len(converted_items) * train_ratio)
        train_items = converted_items[:split_idx]
        eval_items = converted_items[split_idx:]

        self.stats.train_count = len(train_items)
        self.stats.eval_count = len(eval_items)

        # 출력 디렉토리 생성
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 파일 저장
        train_path = output_path / "train.json"
        eval_path = output_path / "eval.json"
        full_path = output_path / "full_dataset.json"
        stats_path = output_path / "conversion_stats.json"

        logger.info(f"Saving train set: {train_path} ({len(train_items)} items)")
        with open(train_path, 'w', encoding='utf-8') as f:
            json.dump(train_items, f, ensure_ascii=False, indent=2)

        logger.info(f"Saving eval set: {eval_path} ({len(eval_items)} items)")
        with open(eval_path, 'w', encoding='utf-8') as f:
            json.dump(eval_items, f, ensure_ascii=False, indent=2)

        logger.info(f"Saving full dataset: {full_path}")
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(converted_items, f, ensure_ascii=False, indent=2)

        # 통계 저장
        stats_dict = asdict(self.stats)
        stats_dict["created_at"] = datetime.now().isoformat()
        stats_dict["input_file"] = str(input_path)
        stats_dict["output_dir"] = str(output_dir)
        stats_dict["train_ratio"] = train_ratio
        stats_dict["augment"] = augment

        logger.info(f"Saving stats: {stats_path}")
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats_dict, f, ensure_ascii=False, indent=2)

        return self.stats

    def convert_by_product(
        self,
        input_path: str,
        output_dir: str,
        train_ratio: float = 0.8,
        augment: bool = False,
        seed: int = 42,
        min_samples: int = 10,
    ) -> Dict[str, ConversionStats]:
        """
        Multi-LoRA v2 학습을 위해 제품별로 분리된 데이터셋 생성

        Args:
            input_path: 입력 learning_dataset.json 경로
            output_dir: 출력 디렉토리 (하위에 제품별 폴더 생성)
            train_ratio: Train/Eval 분할 비율
            augment: 데이터 증강 여부
            seed: 랜덤 시드
            min_samples: 최소 샘플 수 (이보다 적으면 unknown에 병합)

        Returns:
            제품별 ConversionStats 딕셔너리
        """
        random.seed(seed)

        # 입력 파일 로드
        logger.info(f"Loading input file: {input_path}")
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        items = data if isinstance(data, list) else data.get("items", [])
        logger.info(f"Loaded {len(items)} items")

        # 제품별로 데이터 분류
        product_items: Dict[str, List[Dict]] = {name: [] for name in MULTI_LORA_PRODUCTS.keys()}
        product_items["unknown"] = []

        for item in items:
            raw_product = item.get("product", "Unknown")
            source_file = item.get("source_file", "")
            normalized = normalize_product_name(raw_product, source_file)

            # ChatML 형식으로 변환 (제품별 시스템 프롬프트 적용)
            result = self.convert_item(item, 0, product=normalized)
            if result:
                # 제품 정보 추가
                result["_product"] = normalized
                result["_raw_product"] = raw_product
                product_items[normalized].append(result)

                # 데이터 증강
                if augment:
                    item_type = item.get("type", "concept")
                    description = item.get("description", "")
                    lang = self.detect_language(description)
                    templates = self.templates.get_all_templates(item_type, lang)
                    for i in range(1, len(templates)):
                        aug_result = self.convert_item(item, i, product=normalized)
                        if aug_result:
                            aug_result["_product"] = normalized
                            aug_result["_raw_product"] = raw_product
                            product_items[normalized].append(aug_result)

        # 최소 샘플 수 미달 제품은 unknown으로 병합
        for product_name, items_list in list(product_items.items()):
            if product_name != "unknown":
                config = MULTI_LORA_PRODUCTS.get(product_name, {})
                threshold = config.get("min_samples", min_samples)
                if len(items_list) < threshold:
                    logger.warning(f"{product_name}: {len(items_list)} samples < {threshold} threshold, merging to unknown")
                    product_items["unknown"].extend(items_list)
                    product_items[product_name] = []

        # 출력 디렉토리 생성
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 제품별로 저장
        all_stats: Dict[str, ConversionStats] = {}
        summary = {
            "total_products": 0,
            "total_samples": 0,
            "products": {},
            "created_at": datetime.now().isoformat(),
        }

        for product_name, items_list in product_items.items():
            if not items_list:
                continue

            # 제품별 통계
            stats = ConversionStats()
            stats.total = len(items_list)
            stats.converted = len(items_list)

            # 언어/타입 통계
            for item in items_list:
                text = item.get("text", "")
                lang = self.detect_language(text)
                stats.by_language[lang] = stats.by_language.get(lang, 0) + 1

            # 셔플 및 분할
            random.shuffle(items_list)
            split_idx = int(len(items_list) * train_ratio)
            train_items = items_list[:split_idx]
            eval_items = items_list[split_idx:]

            stats.train_count = len(train_items)
            stats.eval_count = len(eval_items)

            # 제품별 디렉토리 생성
            product_dir = output_path / product_name
            product_dir.mkdir(parents=True, exist_ok=True)

            # _product, _raw_product 필드 제거 후 저장
            clean_train = [{k: v for k, v in item.items() if not k.startswith("_")} for item in train_items]
            clean_eval = [{k: v for k, v in item.items() if not k.startswith("_")} for item in eval_items]

            train_path = product_dir / "train.json"
            eval_path = product_dir / "eval.json"
            stats_path = product_dir / "stats.json"

            logger.info(f"Saving {product_name}: train={len(clean_train)}, eval={len(clean_eval)}")

            with open(train_path, 'w', encoding='utf-8') as f:
                json.dump(clean_train, f, ensure_ascii=False, indent=2)

            with open(eval_path, 'w', encoding='utf-8') as f:
                json.dump(clean_eval, f, ensure_ascii=False, indent=2)

            # 제품별 통계 저장
            stats_dict = asdict(stats)
            stats_dict["product"] = product_name
            stats_dict["train_file"] = str(train_path)
            stats_dict["eval_file"] = str(eval_path)

            with open(stats_path, 'w', encoding='utf-8') as f:
                json.dump(stats_dict, f, ensure_ascii=False, indent=2)

            all_stats[product_name] = stats
            summary["total_products"] += 1
            summary["total_samples"] += stats.total
            summary["products"][product_name] = {
                "total": stats.total,
                "train": stats.train_count,
                "eval": stats.eval_count,
            }

        # 전체 요약 저장
        summary_path = output_path / "multi_lora_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        logger.info(f"Multi-LoRA conversion complete: {summary['total_products']} products, {summary['total_samples']} total samples")
        logger.info(f"Summary saved to: {summary_path}")

        return all_stats


def main():
    parser = argparse.ArgumentParser(description="Convert learning dataset to QLoRA format")
    parser.add_argument("--input", "-i", required=True, help="Input learning_dataset.json path")
    parser.add_argument("--output", "-o", required=True, help="Output directory")
    parser.add_argument("--templates", "-t", default=None, help="Question templates JSON path")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Train/eval split ratio (default: 0.8)")
    parser.add_argument("--augment", action="store_true", help="Enable data augmentation")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--split-by-product", action="store_true",
                        help="Split dataset by product for Multi-LoRA v2 training")
    parser.add_argument("--min-samples", type=int, default=10,
                        help="Minimum samples per product (default: 10, smaller merged to unknown)")

    args = parser.parse_args()

    # 템플릿 경로 기본값
    if args.templates is None:
        script_dir = Path(__file__).parent
        args.templates = script_dir / "templates" / "question_templates.json"

    if not os.path.exists(args.templates):
        logger.error(f"Templates file not found: {args.templates}")
        sys.exit(1)

    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    # 변환 실행
    converter = QLoRAConverter(str(args.templates))

    if args.split_by_product:
        # Multi-LoRA v2 제품별 분리 모드
        all_stats = converter.convert_by_product(
            input_path=args.input,
            output_dir=args.output,
            train_ratio=args.train_ratio,
            augment=args.augment,
            seed=args.seed,
            min_samples=args.min_samples,
        )

        # 결과 출력
        print("\n" + "=" * 70)
        print("Multi-LoRA v2 Dataset Conversion Complete")
        print("=" * 70)
        print(f"{'Product':<30} {'Total':>8} {'Train':>8} {'Eval':>8}")
        print("-" * 70)

        total_all = 0
        train_all = 0
        eval_all = 0
        for product, stats in sorted(all_stats.items(), key=lambda x: -x[1].total):
            print(f"{product:<30} {stats.total:>8} {stats.train_count:>8} {stats.eval_count:>8}")
            total_all += stats.total
            train_all += stats.train_count
            eval_all += stats.eval_count

        print("-" * 70)
        print(f"{'TOTAL':<30} {total_all:>8} {train_all:>8} {eval_all:>8}")
        print("=" * 70)
        print(f"\nOutput: {args.output}")
        print(f"Products: {len(all_stats)}")
        print("\nTo train all adapters:")
        print(f"  for product in {args.output}/*/; do")
        print(f"    python qlora_trainer.py --dataset $product/train.json --eval $product/eval.json --output /opt/kms/models/qlora_adapters/$(basename $product)")
        print("  done")

    else:
        # 기존 단일 데이터셋 모드
        stats = converter.convert(
            input_path=args.input,
            output_dir=args.output,
            train_ratio=args.train_ratio,
            augment=args.augment,
            seed=args.seed
        )

        # 결과 출력
        print("\n" + "=" * 60)
        print("QLoRA Format Conversion Complete")
        print("=" * 60)
        print(f"Total items:     {stats.total}")
        print(f"Converted:       {stats.converted}")
        print(f"Skipped:         {stats.skipped}")
        print(f"Augmented:       {stats.augmented}")
        print(f"Train set:       {stats.train_count}")
        print(f"Eval set:        {stats.eval_count}")
        print("-" * 60)
        print("By Type:")
        for t, c in sorted(stats.by_type.items(), key=lambda x: -x[1]):
            print(f"  {t}: {c}")
        print("-" * 60)
        print("By Language:")
        for l, c in sorted(stats.by_language.items(), key=lambda x: -x[1]):
            print(f"  {l}: {c}")
        print("=" * 60)


if __name__ == "__main__":
    main()
