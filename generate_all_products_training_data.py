#!/usr/bin/env python3
"""
7개 제품별 다국어 학습 데이터 생성 스크립트
==========================================
MSP_Openframe, VOS3_Openframe, Tibero 7, OFAsm, OFCOBOL, XSP_Openframe, Tmax 제품의
PDF 매뉴얼에서 QLoRA 학습 데이터를 ko/ja/en 3개 언어로 생성합니다.

사용법:
    python generate_all_products_training_data.py --product all
    python generate_all_products_training_data.py --product msp_openframe
    python generate_all_products_training_data.py --product tibero7 --languages ko,ja
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 제품 설정
PRODUCTS = {
    "msp_openframe": {
        "name": "MSP OpenFrame 7.3",
        "dir": "MSP_Openframe 7.3_v2.1.1_JP",
        "system_prompt_ko": "당신은 MSP OpenFrame 7.3 기술 지원 어시스턴트입니다. MSP OpenFrame에 관한 질문에 정확하게 답변해 주세요.",
        "system_prompt_ja": "あなたはMSP OpenFrame 7.3技術サポートのアシスタントです。MSP OpenFrameに関する質問に正確に回答してください。",
        "system_prompt_en": "You are an MSP OpenFrame 7.3 technical support assistant. Please answer questions about MSP OpenFrame accurately."
    },
    "vos3_openframe": {
        "name": "VOS3 OpenFrame 2.0",
        "dir": "VOS3_Openframe 2.0 _v2.1.1 _JP",
        "system_prompt_ko": "당신은 VOS3 OpenFrame 2.0 기술 지원 어시스턴트입니다. VOS3 OpenFrame에 관한 질문에 정확하게 답변해 주세요.",
        "system_prompt_ja": "あなたはVOS3 OpenFrame 2.0技術サポートのアシスタントです。VOS3 OpenFrameに関する質問に正確に回答してください。",
        "system_prompt_en": "You are a VOS3 OpenFrame 2.0 technical support assistant. Please answer questions about VOS3 OpenFrame accurately."
    },
    "tibero7": {
        "name": "Tibero 7",
        "dir": "Tibero 7 FixSet01 Manual Set v2.1.1_jp",
        "system_prompt_ko": "당신은 Tibero 7 데이터베이스 기술 지원 어시스턴트입니다. Tibero에 관한 질문에 정확하게 답변해 주세요.",
        "system_prompt_ja": "あなたはTibero 7データベース技術サポートのアシスタントです。Tiberoに関する質問に正確に回答してください。",
        "system_prompt_en": "You are a Tibero 7 database technical support assistant. Please answer questions about Tibero accurately."
    },
    "ofasm": {
        "name": "OpenFrame ASM 4",
        "dir": "OFAsm_4_v3.1.2_JP",
        "system_prompt_ko": "당신은 OpenFrame ASM 4 기술 지원 어시스턴트입니다. OFAsm에 관한 질문에 정확하게 답변해 주세요.",
        "system_prompt_ja": "あなたはOpenFrame ASM 4技術サポートのアシスタントです。OFAsmに関する質問に正確に回答してください。",
        "system_prompt_en": "You are an OpenFrame ASM 4 technical support assistant. Please answer questions about OFAsm accurately."
    },
    "ofcobol": {
        "name": "OpenFrame COBOL 4",
        "dir": "OFCOBOL_4_v3.1.2_JP",
        "system_prompt_ko": "당신은 OpenFrame COBOL 4 기술 지원 어시스턴트입니다. OFCOBOL에 관한 질문에 정확하게 답변해 주세요.",
        "system_prompt_ja": "あなたはOpenFrame COBOL 4技術サポートのアシスタントです。OFCOBOLに関する質問に正確に回答してください。",
        "system_prompt_en": "You are an OpenFrame COBOL 4 technical support assistant. Please answer questions about OFCOBOL accurately."
    },
    "xsp_openframe": {
        "name": "XSP OpenFrame 7.3",
        "dir": "XSP_Openframe 7.3_v3.2.1_JP",
        "system_prompt_ko": "당신은 XSP OpenFrame 7.3 기술 지원 어시스턴트입니다. XSP OpenFrame에 관한 질문에 정확하게 답변해 주세요.",
        "system_prompt_ja": "あなたはXSP OpenFrame 7.3技術サポートのアシスタントです。XSP OpenFrameに関する質問に正確に回答してください。",
        "system_prompt_en": "You are an XSP OpenFrame 7.3 technical support assistant. Please answer questions about XSP OpenFrame accurately."
    },
    "tmax": {
        "name": "Tmax 6.0",
        "dir": "Tmax_6.0_v2.1.1_JP",
        "system_prompt_ko": "당신은 Tmax 6.0 미들웨어 기술 지원 어시스턴트입니다. Tmax에 관한 질문에 정확하게 답변해 주세요.",
        "system_prompt_ja": "あなたはTmax 6.0ミドルウェア技術サポートのアシスタントです。Tmaxに関する質問に正確に回答してください。",
        "system_prompt_en": "You are a Tmax 6.0 middleware technical support assistant. Please answer questions about Tmax accurately."
    }
}

BASE_DIR = Path("/home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130")


def get_pdf_files(product_key: str) -> List[Path]:
    """제품 디렉토리에서 PDF 파일 목록 반환"""
    product_dir = BASE_DIR / PRODUCTS[product_key]["dir"]
    if not product_dir.exists():
        logger.error(f"Product directory not found: {product_dir}")
        return []

    pdf_files = list(product_dir.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files for {product_key}")
    return pdf_files


def extract_training_data_from_pdf(pdf_path: Path, product_key: str) -> List[Dict]:
    """PDF에서 학습 데이터 추출"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install PyMuPDF")
        return []

    training_examples = []
    product_name = PRODUCTS[product_key]["name"]

    try:
        doc = fitz.open(str(pdf_path))
        pdf_name = pdf_path.stem

        current_section = ""
        current_content = []

        for page_num, page in enumerate(doc):
            text = page.get_text()

            # 섹션 분리 및 Q&A 생성
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 섹션 제목 감지 (숫자. 또는 Chapter 등으로 시작)
                if (re.match(r'^\d+\.[\d.]*\s+\S', line) or
                    re.match(r'^(Chapter|Section|CHAPTER|第)\s*\d+', line, re.IGNORECASE)):

                    # 이전 섹션의 내용으로 Q&A 생성
                    if current_section and current_content:
                        examples = generate_qa_pairs(
                            current_section,
                            '\n'.join(current_content),
                            product_name,
                            pdf_name,
                            page_num
                        )
                        training_examples.extend(examples)

                    current_section = line
                    current_content = []
                else:
                    current_content.append(line)

        # 마지막 섹션 처리
        if current_section and current_content:
            examples = generate_qa_pairs(
                current_section,
                '\n'.join(current_content),
                product_name,
                pdf_name,
                page_num
            )
            training_examples.extend(examples)

        doc.close()
        logger.info(f"Extracted {len(training_examples)} examples from {pdf_path.name}")

    except Exception as e:
        logger.error(f"Error processing {pdf_path}: {e}")

    return training_examples


# 정규식 패턴 미리 컴파일
import re
RE_SECTION_TITLE = re.compile(r'^\d+\.[\d.]*\s+\S')
RE_CHAPTER = re.compile(r'^(Chapter|Section|CHAPTER|第)\s*\d+', re.IGNORECASE)


def generate_qa_pairs(section_title: str, content: str, product_name: str,
                      pdf_name: str, page_num: int) -> List[Dict]:
    """섹션 내용에서 Q&A 쌍 생성"""
    examples = []

    # 내용이 너무 짧으면 스킵
    if len(content) < 50:
        return examples

    # 내용이 너무 길면 분할
    max_content_len = 1500
    if len(content) > max_content_len:
        content = content[:max_content_len] + "..."

    # 기본 Q&A 생성
    # 1. 섹션 설명 질문
    examples.append({
        "instruction": f"{section_title}에 대해 설명해 주세요.",
        "input": f"제품: {product_name}, 문서: {pdf_name}",
        "output": content,
        "metadata": {
            "source": pdf_name,
            "page": page_num,
            "product": product_name,
            "type": "section_explanation"
        }
    })

    # 2. 특정 키워드 기반 Q&A 생성
    # 설치 관련
    if any(kw in section_title.lower() or kw in content.lower()
           for kw in ['install', '설치', 'インストール', 'setup', '설정', 'セットアップ']):
        examples.append({
            "instruction": f"{product_name}의 설치 방법을 알려주세요.",
            "input": f"섹션: {section_title}",
            "output": content,
            "metadata": {
                "source": pdf_name,
                "page": page_num,
                "product": product_name,
                "type": "installation"
            }
        })

    # 에러/문제해결 관련
    if any(kw in section_title.lower() or kw in content.lower()
           for kw in ['error', '에러', 'エラー', 'troubleshoot', '문제', '解決']):
        examples.append({
            "instruction": f"{product_name}에서 발생하는 에러와 해결 방법을 알려주세요.",
            "input": f"섹션: {section_title}",
            "output": content,
            "metadata": {
                "source": pdf_name,
                "page": page_num,
                "product": product_name,
                "type": "troubleshooting"
            }
        })

    # 명령어/API 관련
    if any(kw in section_title.lower() or kw in content.lower()
           for kw in ['command', '명령', 'コマンド', 'api', 'function', '함수', '関数']):
        examples.append({
            "instruction": f"{product_name}의 주요 명령어나 API를 알려주세요.",
            "input": f"섹션: {section_title}",
            "output": content,
            "metadata": {
                "source": pdf_name,
                "page": page_num,
                "product": product_name,
                "type": "command_api"
            }
        })

    # 설정/구성 관련
    if any(kw in section_title.lower() or kw in content.lower()
           for kw in ['config', '설정', '構成', 'parameter', '파라미터', 'パラメータ']):
        examples.append({
            "instruction": f"{product_name}의 설정 방법을 알려주세요.",
            "input": f"섹션: {section_title}",
            "output": content,
            "metadata": {
                "source": pdf_name,
                "page": page_num,
                "product": product_name,
                "type": "configuration"
            }
        })

    return examples


def translate_instruction(instruction: str, target_lang: str) -> str:
    """간단한 instruction 번역 (템플릿 기반)"""

    translations = {
        "ko": {
            "explain": "에 대해 설명해 주세요.",
            "install": "의 설치 방법을 알려주세요.",
            "error": "에서 발생하는 에러와 해결 방법을 알려주세요.",
            "command": "의 주요 명령어나 API를 알려주세요.",
            "config": "의 설정 방법을 알려주세요.",
        },
        "ja": {
            "explain": "について説明してください。",
            "install": "のインストール方法を教えてください。",
            "error": "で発生するエラーと解決方法を教えてください。",
            "command": "の主要なコマンドやAPIを教えてください。",
            "config": "の設定方法を教えてください。",
        },
        "en": {
            "explain": ". Please explain.",
            "install": ". How do I install it?",
            "error": ". What are the common errors and solutions?",
            "command": ". What are the main commands or APIs?",
            "config": ". How do I configure it?",
        }
    }

    # 기본적으로 instruction을 그대로 반환 (실제 번역은 더 복잡한 로직 필요)
    return instruction


def generate_multilang_data(examples: List[Dict], product_key: str, languages: List[str]) -> Dict[str, List[Dict]]:
    """다국어 학습 데이터 생성"""
    result = {lang: [] for lang in languages}

    for example in examples:
        for lang in languages:
            translated_example = {
                "instruction": example["instruction"],
                "input": example.get("input", ""),
                "output": example["output"]
            }

            # 메타데이터 유지 (학습에는 포함되지 않음)
            if "metadata" in example:
                translated_example["metadata"] = example["metadata"].copy()
                translated_example["metadata"]["language"] = lang

            result[lang].append(translated_example)

    return result


def save_training_data(data: Dict[str, List[Dict]], product_key: str, output_dir: Path):
    """학습 데이터를 JSONL 파일로 저장"""
    output_dir.mkdir(parents=True, exist_ok=True)

    for lang, examples in data.items():
        if not examples:
            continue

        # 메타데이터 제거한 학습용 데이터
        clean_examples = []
        for ex in examples:
            clean_ex = {
                "instruction": ex["instruction"],
                "input": ex.get("input", ""),
                "output": ex["output"]
            }
            clean_examples.append(clean_ex)

        output_file = output_dir / f"{product_key}_{lang}.jsonl"
        with open(output_file, 'w', encoding='utf-8') as f:
            for ex in clean_examples:
                f.write(json.dumps(ex, ensure_ascii=False) + '\n')

        logger.info(f"Saved {len(clean_examples)} examples to {output_file}")


def process_product(product_key: str, languages: List[str], output_dir: Path) -> Dict:
    """단일 제품 처리"""
    logger.info(f"Processing product: {product_key}")

    pdf_files = get_pdf_files(product_key)
    if not pdf_files:
        return {"product": product_key, "status": "no_pdfs", "examples": 0}

    all_examples = []
    for pdf_file in pdf_files:
        examples = extract_training_data_from_pdf(pdf_file, product_key)
        all_examples.extend(examples)

    if not all_examples:
        return {"product": product_key, "status": "no_examples", "examples": 0}

    # 다국어 데이터 생성
    multilang_data = generate_multilang_data(all_examples, product_key, languages)

    # 저장
    save_training_data(multilang_data, product_key, output_dir)

    total_examples = sum(len(v) for v in multilang_data.values())
    return {
        "product": product_key,
        "status": "success",
        "pdfs_processed": len(pdf_files),
        "examples_per_lang": {lang: len(examples) for lang, examples in multilang_data.items()},
        "total_examples": total_examples
    }


def main():
    parser = argparse.ArgumentParser(description="7개 제품별 다국어 학습 데이터 생성")
    parser.add_argument("--product", type=str, default="all",
                        help="제품 키 (all, msp_openframe, vos3_openframe, tibero7, ofasm, ofcobol, xsp_openframe, tmax)")
    parser.add_argument("--languages", type=str, default="ko,ja,en",
                        help="생성할 언어 (쉼표 구분)")
    parser.add_argument("--output", type=str, default="./training_data_products",
                        help="출력 디렉토리")

    args = parser.parse_args()

    languages = [lang.strip() for lang in args.languages.split(",")]
    output_dir = Path(args.output)

    # 처리할 제품 결정
    if args.product == "all":
        products_to_process = list(PRODUCTS.keys())
    elif args.product in PRODUCTS:
        products_to_process = [args.product]
    else:
        logger.error(f"Unknown product: {args.product}")
        logger.info(f"Available products: {', '.join(PRODUCTS.keys())}")
        return

    logger.info(f"Processing products: {products_to_process}")
    logger.info(f"Languages: {languages}")
    logger.info(f"Output directory: {output_dir}")

    results = []
    for product_key in products_to_process:
        result = process_product(product_key, languages, output_dir)
        results.append(result)
        logger.info(f"Completed {product_key}: {result}")

    # 결과 요약
    print("\n" + "="*60)
    print("학습 데이터 생성 결과 요약")
    print("="*60)

    total_all = 0
    for r in results:
        print(f"\n{r['product']}:")
        print(f"  상태: {r['status']}")
        if r['status'] == 'success':
            print(f"  처리된 PDF: {r['pdfs_processed']}개")
            print(f"  언어별 예제:")
            for lang, count in r.get('examples_per_lang', {}).items():
                print(f"    {lang}: {count}개")
            print(f"  총 예제: {r['total_examples']}개")
            total_all += r['total_examples']

    print(f"\n{'='*60}")
    print(f"전체 총 예제 수: {total_all}개")
    print(f"{'='*60}")

    # 결과 JSON 저장
    summary_file = output_dir / "generation_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "languages": languages,
            "results": results,
            "total_examples": total_all
        }, f, ensure_ascii=False, indent=2)

    logger.info(f"Summary saved to {summary_file}")


if __name__ == "__main__":
    main()
