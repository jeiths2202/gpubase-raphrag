#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenFrame 매뉴얼 QLoRA 학습 데이터 추출기
===========================================
TmaxSoft 기술 문서에서 instruction-response 쌍을 생성합니다.

사용법:
  1. PDF 파싱 모드: python openframe_qlora_full_extractor.py --input manual.pdf --output data.jsonl
  2. 샘플 생성 모드: python openframe_qlora_full_extractor.py --sample
  
요구사항:
  - Python 3.8+
  - PyMuPDF 또는 pdfplumber (PDF 파싱시)

출력 형식:
  - Alpaca: {"instruction": "...", "input": "", "output": "..."}
  - ShareGPT: {"conversations": [{"from": "human", "value": "..."}, {"from": "gpt", "value": "..."}]}
"""

import json
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from datetime import datetime

# PDF 처리를 위한 라이브러리 (선택적)
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


class ContentType(Enum):
    """콘텐츠 유형 분류"""
    CHAPTER = "chapter"
    SECTION = "section"
    SUBSECTION = "subsection"
    DEFINITION = "definition"
    PROCEDURE = "procedure"
    CODE_EXAMPLE = "code_example"
    TABLE = "table"
    CONFIGURATION = "configuration"
    COMMAND = "command"
    ERROR_MESSAGE = "error_message"
    LOG = "log"
    API = "api"


@dataclass
class TrainingExample:
    """QLoRA 학습용 데이터 구조"""
    instruction: str
    input: str
    output: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """전체 데이터 딕셔너리 변환"""
        return {
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output,
            "metadata": self.metadata
        }
    
    def to_alpaca_format(self) -> Dict[str, str]:
        """Alpaca 형식으로 변환 (LLaMA Fine-tuning용)"""
        return {
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output
        }
    
    def to_sharegpt_format(self) -> Dict[str, Any]:
        """ShareGPT 형식으로 변환 (ChatGPT-like 학습용)"""
        messages = []
        if self.input:
            messages.append({
                "from": "human",
                "value": f"{self.instruction}\n\n{self.input}"
            })
        else:
            messages.append({
                "from": "human", 
                "value": self.instruction
            })
        messages.append({
            "from": "gpt",
            "value": self.output
        })
        return {"conversations": messages}
    
    def to_openai_format(self) -> Dict[str, Any]:
        """OpenAI Fine-tuning 형식으로 변환"""
        messages = []
        messages.append({
            "role": "system",
            "content": "あなたはOpenFrame技術サポートのアシスタントです。OpenFrameに関する質問に正確に回答してください。"
        })
        
        user_content = self.instruction
        if self.input:
            user_content += f"\n\n{self.input}"
        
        messages.append({"role": "user", "content": user_content})
        messages.append({"role": "assistant", "content": self.output})
        
        return {"messages": messages}
    
    def get_id(self) -> str:
        """고유 ID 생성"""
        content = f"{self.instruction}{self.input}{self.output}"
        return hashlib.md5(content.encode()).hexdigest()[:12]


@dataclass 
class DocumentSection:
    """문서 섹션 구조"""
    level: int  # 1: 章, 2: 節, 3: 項
    number: str  # "1.1", "A.2" 등
    title: str
    content: str
    content_type: ContentType
    parent_section: Optional[str] = None
    code_blocks: List[str] = field(default_factory=list)
    tables: List[Dict] = field(default_factory=list)
    page_number: Optional[int] = None


class OpenFrameManualParser:
    """OpenFrame 매뉴얼 파서 - PDF 및 텍스트 지원"""
    
    # 섹션 패턴 (일본어/영어 혼합)
    CHAPTER_PATTERN = re.compile(r'^第(\d+)章\s+(.+)$', re.MULTILINE)
    SECTION_PATTERN = re.compile(r'^(\d+\.\d+\.?)\s+(.+)$', re.MULTILINE)
    SUBSECTION_PATTERN = re.compile(r'^(\d+\.\d+\.\d+\.?)\s+(.+)$', re.MULTILINE)
    APPENDIX_PATTERN = re.compile(r'^付録\s*([A-Z])\.?\s+(.+)$', re.MULTILINE)
    
    # 코드 블록 패턴
    CODE_BLOCK_PATTERN = re.compile(r'^\$\s+.+$|^[A-Z_]+\s*=.+$', re.MULTILINE)
    CONFIG_PATTERN = re.compile(r'^\[.+\]$', re.MULTILINE)
    SQL_PATTERN = re.compile(r'^SQL>\s*.+$', re.MULTILINE)
    
    # 키워드 기반 콘텐츠 유형 매핑
    CONTENT_TYPE_KEYWORDS = {
        ContentType.DEFINITION: ['概要', 'overview', '紹介', 'introduction', 'とは'],
        ContentType.CONFIGURATION: ['設定', 'config', '構成', '環境', 'conf'],
        ContentType.COMMAND: ['コマンド', 'command', 'ツール', 'tool', 'mgr'],
        ContentType.PROCEDURE: ['手順', 'procedure', '方法', '作成', '実行'],
        ContentType.ERROR_MESSAGE: ['エラー', 'error', 'メッセージ'],
        ContentType.LOG: ['ログ', 'log', '記録'],
        ContentType.API: ['API', 'サービス', 'service', 'svr']
    }
    
    def __init__(self):
        self.sections: List[DocumentSection] = []
        self.document_metadata: Dict[str, Any] = {}
        
    def parse_pdf(self, pdf_path: str) -> List[DocumentSection]:
        """PDF 파일 파싱"""
        if HAS_PYMUPDF:
            return self._parse_with_pymupdf(pdf_path)
        elif HAS_PDFPLUMBER:
            return self._parse_with_pdfplumber(pdf_path)
        else:
            raise ImportError(
                "PDF 파싱을 위해 PyMuPDF 또는 pdfplumber가 필요합니다.\n"
                "설치: pip install PyMuPDF 또는 pip install pdfplumber"
            )
    
    def _parse_with_pymupdf(self, pdf_path: str) -> List[DocumentSection]:
        """PyMuPDF로 PDF 파싱"""
        doc = fitz.open(pdf_path)
        full_text = ""
        
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text()
            full_text += f"\n[PAGE:{page_num}]\n{page_text}"
        
        doc.close()
        return self._parse_text(full_text)
    
    def _parse_with_pdfplumber(self, pdf_path: str) -> List[DocumentSection]:
        """pdfplumber로 PDF 파싱"""
        full_text = ""
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    full_text += f"\n[PAGE:{page_num}]\n{text}"
        
        return self._parse_text(full_text)
    
    def parse_text(self, text: str) -> List[DocumentSection]:
        """텍스트 직접 파싱 (외부 호출용)"""
        return self._parse_text(text)
    
    def _parse_text(self, text: str) -> List[DocumentSection]:
        """텍스트 파싱하여 섹션 추출"""
        sections = []
        
        # 문서 메타데이터 추출
        self._extract_metadata(text)
        
        # 챕터 및 부록 매칭
        chapter_matches = [(m, 'chapter') for m in self.CHAPTER_PATTERN.finditer(text)]
        appendix_matches = [(m, 'appendix') for m in self.APPENDIX_PATTERN.finditer(text)]
        
        all_matches = chapter_matches + appendix_matches
        all_matches.sort(key=lambda x: x[0].start())
        
        for i, (match, match_type) in enumerate(all_matches):
            start_pos = match.start()
            end_pos = all_matches[i + 1][0].start() if i + 1 < len(all_matches) else len(text)
            
            chapter_text = text[start_pos:end_pos]
            
            if match_type == 'chapter':
                chapter_num = match.group(1)
                chapter_title = match.group(2).strip()
                section_number = f"第{chapter_num}章"
            else:
                chapter_num = match.group(1)
                chapter_title = match.group(2).strip()
                section_number = f"付録{chapter_num}"
            
            # 챕터 섹션 생성
            chapter_section = DocumentSection(
                level=1,
                number=section_number,
                title=chapter_title,
                content=self._clean_content(chapter_text),
                content_type=ContentType.CHAPTER,
                code_blocks=self._extract_code_blocks(chapter_text)
            )
            sections.append(chapter_section)
            
            # 하위 섹션 파싱
            sub_sections = self._parse_subsections(chapter_text, section_number)
            sections.extend(sub_sections)
        
        self.sections = sections
        return sections
    
    def _parse_subsections(self, chapter_text: str, parent_chapter: str) -> List[DocumentSection]:
        """하위 섹션 파싱"""
        sections = []
        
        # 섹션 매칭 (2레벨)
        section_matches = list(self.SECTION_PATTERN.finditer(chapter_text))
        
        for i, match in enumerate(section_matches):
            start_pos = match.start()
            end_pos = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(chapter_text)
            
            section_text = chapter_text[start_pos:end_pos]
            section_num = match.group(1).rstrip('.')
            section_title = match.group(2).strip()
            
            # 콘텐츠 유형 결정
            content_type = self._determine_content_type(section_title, section_text)
            
            section = DocumentSection(
                level=2,
                number=section_num,
                title=section_title,
                content=self._clean_content(section_text),
                content_type=content_type,
                parent_section=parent_chapter,
                code_blocks=self._extract_code_blocks(section_text),
                tables=self._extract_tables(section_text)
            )
            sections.append(section)
            
            # 서브섹션 파싱 (3레벨)
            subsection_matches = list(self.SUBSECTION_PATTERN.finditer(section_text))
            for j, sub_match in enumerate(subsection_matches):
                sub_start = sub_match.start()
                sub_end = subsection_matches[j + 1].start() if j + 1 < len(subsection_matches) else len(section_text)
                
                subsection_text = section_text[sub_start:sub_end]
                subsection_num = sub_match.group(1).rstrip('.')
                subsection_title = sub_match.group(2).strip()
                
                subsection = DocumentSection(
                    level=3,
                    number=subsection_num,
                    title=subsection_title,
                    content=self._clean_content(subsection_text),
                    content_type=self._determine_content_type(subsection_title, subsection_text),
                    parent_section=section_num,
                    code_blocks=self._extract_code_blocks(subsection_text)
                )
                sections.append(subsection)
        
        return sections
    
    def _determine_content_type(self, title: str, content: str) -> ContentType:
        """콘텐츠 유형 결정"""
        title_content = (title + " " + content[:500]).lower()
        
        for content_type, keywords in self.CONTENT_TYPE_KEYWORDS.items():
            if any(kw.lower() in title_content for kw in keywords):
                return content_type
        
        # 코드 패턴 기반 판단
        if self.CODE_BLOCK_PATTERN.search(content):
            return ContentType.CODE_EXAMPLE
        if self.CONFIG_PATTERN.search(content):
            return ContentType.CONFIGURATION
        if self.SQL_PATTERN.search(content):
            return ContentType.PROCEDURE
        
        return ContentType.SECTION
    
    def _extract_metadata(self, text: str) -> Dict[str, Any]:
        """문서 메타데이터 추출"""
        metadata = {
            "product": "OpenFrame/Base",
            "version": "7.1",
            "language": "ja",
            "extracted_at": datetime.now().isoformat()
        }
        
        # 버전 정보 추출
        version_match = re.search(r'OpenFrame/Base\s+(\d+\.\d+)', text)
        if version_match:
            metadata["version"] = version_match.group(1)
        
        # 발행일 추출
        date_match = re.search(r'発行日:\s*(\d{4}年\d{1,2}月\d{1,2}日)', text)
        if date_match:
            metadata["publish_date"] = date_match.group(1)
        
        # 가이드 버전 추출
        guide_version_match = re.search(r'ガイドバージョン:\s*(v[\d.]+)', text)
        if guide_version_match:
            metadata["guide_version"] = guide_version_match.group(1)
        
        self.document_metadata = metadata
        return metadata
    
    def _extract_code_blocks(self, text: str) -> List[str]:
        """코드 블록 추출"""
        code_blocks = []
        
        # $ 로 시작하는 커맨드라인
        cmd_matches = re.findall(r'^\$\s+.+$', text, re.MULTILINE)
        code_blocks.extend(cmd_matches)
        
        # 설정 블록 (KEY=VALUE 형식)
        config_matches = re.findall(r'^[A-Z_]+\s*=\s*.+$', text, re.MULTILINE)
        code_blocks.extend(config_matches)
        
        # SQL 구문
        sql_matches = re.findall(r'SQL>\s*.+$', text, re.MULTILINE)
        code_blocks.extend(sql_matches)
        
        # 섹션 설정 블록 [SECTION_NAME]
        section_config = re.findall(r'^\[[\w_]+\][\s\S]*?(?=\n\[|\Z)', text, re.MULTILINE)
        for config in section_config[:3]:  # 최대 3개
            if len(config) < 500:  # 너무 긴 블록 제외
                code_blocks.append(config.strip())
        
        return list(set(code_blocks))  # 중복 제거
    
    def _extract_tables(self, text: str) -> List[Dict]:
        """표 데이터 추출 (간단한 구현)"""
        tables = []
        
        # 표 패턴 감지 (항목 | 설명 형식)
        table_pattern = re.compile(r'^([\w\s/]+)\s{2,}(.+)$', re.MULTILINE)
        matches = table_pattern.findall(text)
        
        if len(matches) >= 3:  # 최소 3행 이상이면 표로 인식
            table_data = {
                "rows": [{"key": m[0].strip(), "value": m[1].strip()} for m in matches]
            }
            tables.append(table_data)
        
        return tables
    
    def _clean_content(self, text: str) -> str:
        """콘텐츠 정제"""
        # 페이지 번호 및 헤더/푸터 제거
        text = re.sub(r'\d+\s+OpenFrame\s+Base.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^OpenFrame\s+\d+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[PAGE:\d+\]', '', text)
        
        # 연속 공백/개행 정리
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)
        
        return text.strip()


class QLoRADataGenerator:
    """QLoRA 학습 데이터 생성기"""
    
    # 질문 템플릿 (일본어)
    QUESTION_TEMPLATES_JA = {
        ContentType.DEFINITION: [
            "{title}とは何ですか？",
            "{title}について説明してください。",
            "{title}の概要を教えてください。",
            "{title}の目的と役割は何ですか？"
        ],
        ContentType.CONFIGURATION: [
            "{title}の設定方法を教えてください。",
            "{title}はどのように設定しますか？",
            "{title}の設定例を示してください。",
            "{title}の設定パラメータについて説明してください。"
        ],
        ContentType.COMMAND: [
            "{title}コマンドの使い方を教えてください。",
            "{title}の実行方法を説明してください。",
            "{title}のオプションについて教えてください。",
            "{title}の使用例を示してください。"
        ],
        ContentType.PROCEDURE: [
            "{title}の手順を教えてください。",
            "{title}を実行する方法は？",
            "{title}のステップを詳しく説明してください。",
            "{title}はどのように行いますか？"
        ],
        ContentType.CODE_EXAMPLE: [
            "{title}のコード例を示してください。",
            "{title}の実装例を教えてください。",
            "{title}のサンプルを見せてください。"
        ],
        ContentType.LOG: [
            "{title}について説明してください。",
            "{title}の形式を教えてください。",
            "{title}はどこに保存されますか？"
        ],
        ContentType.API: [
            "{title}の機能について説明してください。",
            "{title}サーバーの役割は何ですか？",
            "{title}の設定方法を教えてください。"
        ],
        ContentType.CHAPTER: [
            "{title}について説明してください。",
            "{title}の内容を要約してください。",
            "{title}で扱うトピックは何ですか？"
        ],
        ContentType.SECTION: [
            "{title}について詳しく教えてください。",
            "{title}とは何ですか？"
        ]
    }
    
    # 질문 템플릿 (영어)
    QUESTION_TEMPLATES_EN = {
        ContentType.DEFINITION: [
            "What is {title}?",
            "Explain {title}.",
            "Describe the overview of {title}.",
            "What is the purpose of {title}?"
        ],
        ContentType.CONFIGURATION: [
            "How to configure {title}?",
            "Show me the configuration example of {title}.",
            "Explain the configuration parameters of {title}."
        ],
        ContentType.COMMAND: [
            "How to use {title} command?",
            "Show the usage of {title}.",
            "Explain the options of {title}.",
            "Give me examples of {title}."
        ],
        ContentType.PROCEDURE: [
            "What are the steps for {title}?",
            "How to perform {title}?",
            "Explain the procedure of {title}."
        ],
        ContentType.CODE_EXAMPLE: [
            "Show me code examples for {title}.",
            "Provide implementation examples of {title}."
        ],
        ContentType.LOG: [
            "Explain {title}.",
            "What is the format of {title}?",
            "Where is {title} stored?"
        ],
        ContentType.API: [
            "What are the features of {title}?",
            "What is the role of {title} server?",
            "How to configure {title}?"
        ],
        ContentType.CHAPTER: [
            "Explain {title}.",
            "Summarize the content of {title}.",
            "What topics are covered in {title}?"
        ],
        ContentType.SECTION: [
            "Tell me more about {title}.",
            "What is {title}?"
        ]
    }
    
    def __init__(self, parser: OpenFrameManualParser):
        self.parser = parser
        self.training_data: List[TrainingExample] = []
        
    def generate_training_data(self, 
                               include_metadata: bool = True,
                               language: str = "ja",
                               min_content_length: int = 50,
                               max_templates_per_section: int = 3) -> List[TrainingExample]:
        """학습 데이터 생성
        
        Args:
            include_metadata: 메타데이터 포함 여부
            language: 질문 언어 (ja/en)
            min_content_length: 최소 콘텐츠 길이
            max_templates_per_section: 섹션당 최대 질문 템플릿 수
        """
        training_data = []
        
        templates = self.QUESTION_TEMPLATES_JA if language == "ja" else self.QUESTION_TEMPLATES_EN
        
        for section in self.parser.sections:
            # 콘텐츠 길이 체크
            if len(section.content) < min_content_length:
                continue
            
            # 해당 콘텐츠 유형의 템플릿 가져오기
            section_templates = templates.get(
                section.content_type, 
                templates.get(ContentType.SECTION, ["{title}について説明してください。"])
            )
            
            # 템플릿 수 제한
            selected_templates = section_templates[:max_templates_per_section]
            
            for template in selected_templates:
                instruction = template.format(title=section.title)
                
                # 메타데이터 구성
                metadata = {}
                if include_metadata:
                    metadata = {
                        "source": "OpenFrame Base Guide",
                        "version": self.parser.document_metadata.get("version", "7.1"),
                        "section_number": section.number,
                        "section_level": section.level,
                        "content_type": section.content_type.value,
                        "parent_section": section.parent_section,
                        "has_code_examples": len(section.code_blocks) > 0,
                        "language": language
                    }
                
                # 응답 생성
                output = self._generate_response(section, language)
                
                example = TrainingExample(
                    instruction=instruction,
                    input="",
                    output=output,
                    metadata=metadata
                )
                
                training_data.append(example)
            
            # 코드 블록이 있으면 추가 예제 생성
            if section.code_blocks:
                code_examples = self._generate_code_examples(section, language, include_metadata)
                training_data.extend(code_examples)
        
        self.training_data = training_data
        return training_data
    
    def _generate_response(self, section: DocumentSection, language: str = "ja") -> str:
        """응답 텍스트 생성"""
        response_parts = []
        
        # 기본 설명
        response_parts.append(section.content)
        
        # 코드 블록 포함
        if section.code_blocks:
            label = "使用例:" if language == "ja" else "Examples:"
            response_parts.append(f"\n\n{label}")
            for code in section.code_blocks[:3]:  # 최대 3개
                response_parts.append(f"```\n{code}\n```")
        
        return "\n".join(response_parts)
    
    def _generate_code_examples(self, section: DocumentSection, 
                                language: str, 
                                include_metadata: bool) -> List[TrainingExample]:
        """코드 예제 관련 학습 데이터 생성"""
        examples = []
        
        if not section.code_blocks:
            return examples
        
        if language == "ja":
            instruction = f"{section.title}のコマンド例・設定例を教えてください。"
        else:
            instruction = f"Show me command and configuration examples for {section.title}."
        
        code_output = "\n".join([f"```\n{code}\n```" for code in section.code_blocks])
        
        metadata = {}
        if include_metadata:
            metadata = {
                "source": "OpenFrame Base Guide",
                "section_number": section.number,
                "content_type": "code_example",
                "language": language
            }
        
        example = TrainingExample(
            instruction=instruction,
            input="",
            output=code_output,
            metadata=metadata
        )
        examples.append(example)
        
        return examples
    
    def generate_qa_pairs(self, language: str = "ja") -> List[TrainingExample]:
        """고급 Q&A 쌍 생성 - 섹션 간 관계 기반"""
        qa_pairs = []
        
        # 챕터별 요약 질문
        for section in self.parser.sections:
            if section.level == 1:  # 챕터 수준
                child_sections = [s for s in self.parser.sections 
                                 if s.parent_section == section.number]
                
                if child_sections:
                    topics = [s.title for s in child_sections[:5]]
                    
                    if language == "ja":
                        instruction = f"{section.title}で扱うトピックは何ですか？"
                        output_prefix = f"{section.title}では以下のトピックを扱います："
                    else:
                        instruction = f"What topics are covered in {section.title}?"
                        output_prefix = f"{section.title} covers the following topics:"
                    
                    qa = TrainingExample(
                        instruction=instruction,
                        input="",
                        output=output_prefix + "\n" + "\n".join([f"- {t}" for t in topics]),
                        metadata={
                            "source": "OpenFrame Base Guide",
                            "question_type": "summary",
                            "section_number": section.number
                        }
                    )
                    qa_pairs.append(qa)
        
        # 관련 개념 연결 질문
        concept_pairs = self._generate_concept_links(language)
        qa_pairs.extend(concept_pairs)
        
        return qa_pairs
    
    def _generate_concept_links(self, language: str) -> List[TrainingExample]:
        """관련 개념 연결 Q&A 생성"""
        concept_links = []
        
        # Tmax와 OpenFrame 관계
        tmax_sections = [s for s in self.parser.sections if 'Tmax' in s.title]
        if tmax_sections:
            if language == "ja":
                qa = TrainingExample(
                    instruction="TmaxとOpenFrameの関係について説明してください。",
                    input="",
                    output="OpenFrameソリューションはTmaxエンジンをベースにしており、マルチ・ノード・クラスタリング、ロードバランシング、フェイルオーバーなどの機能を継承し、既存のメインフレームで提供していた高可用性および安定性を保証します。",
                    metadata={"question_type": "concept_link", "concepts": ["Tmax", "OpenFrame"]}
                )
            else:
                qa = TrainingExample(
                    instruction="Explain the relationship between Tmax and OpenFrame.",
                    input="",
                    output="OpenFrame solution is based on Tmax engine, inheriting features like multi-node clustering, load balancing, and failover to ensure high availability and stability that was provided by existing mainframes.",
                    metadata={"question_type": "concept_link", "concepts": ["Tmax", "OpenFrame"]}
                )
            concept_links.append(qa)
        
        return concept_links
    
    def export_jsonl(self, output_path: str, format_type: str = "alpaca"):
        """JSONL 형식으로 내보내기"""
        with open(output_path, 'w', encoding='utf-8') as f:
            for example in self.training_data:
                if format_type == "alpaca":
                    data = example.to_alpaca_format()
                elif format_type == "sharegpt":
                    data = example.to_sharegpt_format()
                elif format_type == "openai":
                    data = example.to_openai_format()
                else:
                    data = example.to_dict()
                
                f.write(json.dumps(data, ensure_ascii=False) + '\n')
        
        print(f"Exported {len(self.training_data)} examples to {output_path}")
    
    def export_json(self, output_path: str, format_type: str = "alpaca"):
        """JSON 배열 형식으로 내보내기"""
        data_list = []
        
        for example in self.training_data:
            if format_type == "alpaca":
                data_list.append(example.to_alpaca_format())
            elif format_type == "sharegpt":
                data_list.append(example.to_sharegpt_format())
            elif format_type == "openai":
                data_list.append(example.to_openai_format())
            else:
                data_list.append(example.to_dict())
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
        
        print(f"Exported {len(self.training_data)} examples to {output_path}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        stats = {
            "total_examples": len(self.training_data),
            "by_content_type": {},
            "avg_instruction_length": 0,
            "avg_output_length": 0,
            "total_sections": len(self.parser.sections),
            "document_metadata": self.parser.document_metadata
        }
        
        # 콘텐츠 유형별 통계
        for example in self.training_data:
            content_type = example.metadata.get("content_type", "unknown")
            stats["by_content_type"][content_type] = \
                stats["by_content_type"].get(content_type, 0) + 1
        
        # 평균 길이 계산
        if self.training_data:
            stats["avg_instruction_length"] = round(sum(
                len(e.instruction) for e in self.training_data
            ) / len(self.training_data), 1)
            stats["avg_output_length"] = round(sum(
                len(e.output) for e in self.training_data
            ) / len(self.training_data), 1)
        
        return stats


def create_sample_training_data() -> Tuple[List[TrainingExample], Dict[str, Any]]:
    """
    OpenFrame Base Guide 문서 기반 샘플 학습 데이터 생성
    (PDF 없이 문서 내용을 직접 사용)
    """
    
    # 문서에서 추출한 핵심 섹션 데이터
    sample_sections = [
        {
            "number": "1.1",
            "title": "概要",
            "content": """OpenFrameは、メインフレーム環境の業務システムをオープン環境に移行して運用できるようにするリホスト・ソリューションです。移行するアプリケーションの特性に応じて、オンライン業務とバッチ業務に分けられるため、OpenFrameソリューションも、オンライン製品とバッチ製品を提供しています。

OpenFrame/Baseシステムは、OpenFrameのOnlineシステムとBatchシステムで共通して使用されるモジュールとサービスを組み合わせてパッケージとして構成した製品です。したがって、OpenFrame/Baseシステムはオンライン業務とバッチ業務の両システムにインストールされる必要があります。

また、OpenFrame/Baseシステムは、既存のメインフレームで提供していたOSレベルのリソースとサービスをUNIXシステムでエミュレートするレイヤーとして見なすことができます。""",
            "content_type": ContentType.DEFINITION
        },
        {
            "number": "1.2",
            "title": "構成",
            "content": """OpenFrame/Baseシステムは、Tmaxエンジン、データセット、コードページ、コンソールで構成されます。

● Tmaxエンジン
Tmaxは、分散環境システムで異種コンピュータ間のトランザクションを保証し、負荷を分散およびエラーを処理するTPモニター製品です。主な機能は、プロセス管理、トランザクション管理、ロードバランシングおよびフェイルオーバーです。

● データセット
メインフレームでは、OSレベルでレコードの読み書きおよびトランザクションをサポートするさまざまなデータセットを使用できますが、UNIXファイル・システムでは、基本的なブロック単位の読み書き機能のみを提供します。OpenFrame/Baseシステムではリレーショナル・データベース技術を用いて、メインフレームで提供するデータセット機能をオープン環境で使用するためのデータセット・モジュールとサービスを提供します。

● コードページ
一般的にメインフレームでのユーザー・データは、EBCDIC（またはEBCDIK）コードセットで保存されています。一方、OpenFrameでのユーザー・データは、オープン環境の標準であるASCIIコードセットで保存されます。したがって、メインフレームのデータをオープン環境に移行するか、またはメインフレームとの業務連携のためにオープン環境のデータをメインフレームに転送する場合はコードセットの変換が必要です。

● コンソール
システム・コンソールまたはコンソールとは、システム・カーネルからシステム管理者へのメッセージを出力し、システム管理者がシステムを管理するためのコマンドを入力するための画面とキーボードを意味します。""",
            "content_type": ContentType.DEFINITION
        },
        {
            "number": "2.2",
            "title": "Tmaxの紹介",
            "content": """Tmaxは、分散環境システムで異種コンピュータ間のトランザクションを保証し、負荷を分散およびエラーを処理するTPモニター製品です。

以下は、Tmaxの特徴です。
● 分散トランザクション処理の国際標準であるX/Open DTPに準拠します。
● 国際標準化機構(OSI)のDTPサービスに対する機能的な分散と、構成要素間のAPIおよびシステム・インターフェースを定義します。
● 分散環境での異種間の透明な業務処理およびOLTPをサポートします。
● トランザクション処理のACID特性を満たし、最適な開発環境を提供します。""",
            "content_type": ContentType.DEFINITION
        },
        {
            "number": "2.3",
            "title": "OpenFrameとTmax",
            "content": """OpenFrameソリューションはTmaxエンジンをベースにしており、マルチ・ノード・クラスタリング、ロードバランシング、フェイルオーバーなどの機能を継承し、既存のメインフレームで提供していた高可用性および安定性を保証します。

以下は、Tmaxエンジンから継承された特性についての説明です。

● マルチ・ノード・クラスタリング
ドメインは、1つの同一環境を共有するTmaxシステムの構成単位であり、1つ以上のノードで構成することができます。また、ピアツーピア方式で接続されており、クライアントはドメイン内で提供されるすべてのサービスを使用することができます。

● ロードバランシング
Tmaxはクライアントのサービス要求が集中した場合、以下の3つの方法で負荷を分散し、最適なシステム・パフォーマンスとリソースの使用を保証できます。
– システム負荷管理（SLM: System Load Management）
– データ依存ルーティング（DDR: Data Dependent Routing）
– 動的なロードバランシング（DLM: Dynamic Load Balancing）

● フェイルオーバー
Tmaxのフェイルオーバー機能により、OpenFrameシステムの運用中に予期しない障害が発生した場合でも、ユーザーは障害を認識することなく、システムの使用を継続することができます。""",
            "content_type": ContentType.DEFINITION
        },
        {
            "number": "3.1",
            "title": "データセットの紹介",
            "content": """データセットとは、論理的に接続されているデータ・レコードの集合であり、レコードとは、アプリケーションで使用する情報の基本単位です。データセットとUNIXファイルの違いは、データセットを使用する場合は、レコード単位のI/Oをサポートするアクセス・メソッドが提供されることです。

OpenFrame/Baseシステムでのデータセットは、メインフレームと同様にVSAMデータセットと非VSAMデータセットに区分しています。

● VSAMデータセット
メインフレームのVSAM（Virtual Storage Access Method）は、データ処理プログラムで一般的に使用されていた3つの構造（順次、索引付き、直接アクセス）のデータセットを効率的に保存および使用するためのアクセス・メソッドおよびユーティリティ・プログラムです。

● 非VSAMデータセット
VSAMデータセットが開発される前に使用されていたすべてのデータセットを非VSAMデータセットといいます。OpenFrameではUNIXのファイル・システムで対応しています。""",
            "content_type": ContentType.DEFINITION
        },
        {
            "number": "3.2",
            "title": "システム表",
            "content": """OpenFrame/Baseシステムをインストールおよび起動するには、データベースにシステム表が作成される必要があります。システム表は、インストール中に自動的に作成されます。

OpenFrame/Baseシステムを起動するには、次の2つの表が必要です。

● カタログ表
メインフレームでのカタログは、BCS（Basic Catalog Structure、基本カタログ構造）データセットとVVDS（VSAM Volume Data Set、VSAMボリューム・データセット）で構成されます。OpenFrame/Baseでは、BCSデータセットをカタログ表が代替しています。

● VTOC表
メインフレームでのVTOCは、すべてのボリュームに存在するシステム・データセットです。VTOCは、ボリューム領域の割り当て情報と拡張情報を管理しています。""",
            "content_type": ContentType.DEFINITION
        },
        {
            "number": "4.3.1",
            "title": "cpmmgr",
            "content": """cpmmgrツールを実行すると、コマンドを入力できるプロンプトが表示されます。コマンドの省略形を入力することができます。

主なコマンド：
● cc (Change Code Mapping): 現在のCPMデータにマッピングされているコードを指定されたマッピング・コードに変更します。
● cf (Convert File): 現在のCPMデータを使用して特定のファイルを変換します。
● ct (Convert Text): 現在のCPMデータを使用して、指定された文字列または16進の値を変換します。
● pd (Print Double-Byte Code Mapping): 現在CPMデータに保存されている2バイトのコード・マッピング情報を表示します。
● ps (Print Single-Byte Code Mapping): 現在CPMデータに保存されている1バイトのコード・マッピング情報を表示します。
● pr (Print Single/Double Byte Code Range): 現在CPMデータに保存されているコード・マッピング範囲を表示します。""",
            "content_type": ContentType.COMMAND,
            "code_blocks": [
                "$ cpmmgr <file>",
                ">> help"
            ]
        },
        {
            "number": "5.2.1",
            "title": "DISPLAY",
            "content": """PL/I言語のDISPLAY文またはCOBOL言語のDISPLAY UPON CONSOLE文を、コンソールのDISPLAY機能でサポートします。

プログラムでDISPLAYを実行するプロセス：
1. プログラムはofrcmsvrにDISPLAYメッセージを送信します。
2. ofrcmsvrはDISPLAYメッセージをファイルに書き込みます。
3. ofrcmsvrは現在接続されているtconmgrにメッセージを送信します。
4. ofrcmsvrはプログラムに確認応答を返します。""",
            "content_type": ContentType.PROCEDURE,
            "code_blocks": [
                'DISPLAY "CONSOLE DISPLAY TEST" UPON CONSOLE.'
            ]
        },
        {
            "number": "5.2.2",
            "title": "ACCEPT",
            "content": """PL/I言語のREPLY文またはCOBOL言語のACCEPT FROM CONSOLE文を、コンソールのACCEPT機能でサポートします。

プログラムでACCEPTを実行するプロセス：
1. プログラムはofrcmsvrにACCEPTメッセージを送信します。
2. ofrcmsvrはACCEPTメッセージをファイルに書き込みます。
3. ofrcmsvrは現在接続されているtconmgrにメッセージを送信し、tconmgrからのACCEPT応答を受信するまでプログラムへの応答を保留します。""",
            "content_type": ContentType.PROCEDURE,
            "code_blocks": [
                'ACCEPT BUFFER FROM CONSOLE.'
            ]
        },
        {
            "number": "5.3",
            "title": "tconmgr",
            "content": """tconmgrは、メインフレームでのコンソールに対応する仮想のOpenFrameコンソール・ツールです。ユーザーが指定したIDのコンソール・メッセージを確認できます。

入力項目：
● CONSOLE_ID: 0から99まで指定できます。現在OpenFrameでは、0(ゼロ)のみ使用されており、CONSOLE_IDが指定されていない場合は、0として処理されます。

出力項目（コンソール・メッセージの先頭に出力される情報）：
● Msg Source: メッセージのソース(発信元)です。COBOL、TCONMGRなどがあります。
● Date Time: メッセージが作成された日時(YYYYMMDD_HHMMSS形式)です。
● Length: メッセージの長さです。
● Console ID: メッセージのソースのコンソールIDです。
● User: 一般的にメッセージのソースのジョブIDが出力されます。
● Process ID: メッセージのソースのUNIX PIDが出力されます。""",
            "content_type": ContentType.COMMAND,
            "code_blocks": [
                "$ tconmgr [CONSOLE_ID]"
            ]
        },
        {
            "number": "A.2",
            "title": "ofrcmsvr",
            "content": """ofrcmsvrサーバーは、コンソール・メッセージを管理および中継します。ユーザー制御サーバー(UCS)であり、各ドメインは1つのインスタンスを持ちます。""",
            "content_type": ContentType.API,
            "code_blocks": [
                'ofrcmsvr SVGNAME = svg_domain, MIN = 1, MAX = 1, SVRTYPE=UCS,',
                'CLOPT="-o $(SVR)$(DATE).out -e $(SVR)$(DATE).err"'
            ]
        },
        {
            "number": "A.3",
            "title": "ofrdmsvr",
            "content": """ofrdmsvrサーバーは、データセットを管理します。期限切れのデータセットを自動的に削除します。ユーザー制御サーバー(UCS)であり、各ドメインは1つのインスタンスを持ちます。""",
            "content_type": ContentType.API,
            "code_blocks": [
                'ofrdmsvr SVGNAME = svg_domain, MIN = 1, MAX = 1, SVRTYPE=UCS,',
                'CLOPT="-o $(SVR)$(DATE).out -e $(SVR)$(DATE).err"'
            ]
        },
        {
            "number": "A.4",
            "title": "ofrdsedt",
            "content": """ofrdsedtサーバーは、データセットを編集します。OFAdminなどのクライアントから特定のデータセットの編集要求を受け、データセットの割り当てを実行し、データセットのレコード・データをクライアントに返します。会話型のサーバーであり、各ドメインは複数のインスタンスを持つことができます。""",
            "content_type": ContentType.API,
            "code_blocks": [
                'ofrdsedt SVGNAME = svg_node1, CONV=Y,',
                'CLOPT="-o $(SVR)$(DATE).out -e $(SVR)$(DATE).err"'
            ]
        },
        {
            "number": "A.5",
            "title": "ofrlhsvr",
            "content": """ofrlhsvrサーバーは、データセットのロック要求のためのロック・ハンドルを割り当てます。データベースのDBMS_LOCK.ALLOCATE_UNIQUEを介して特定のロック名に対するハンドルを返します。Tmax制御サーバー(TCS)であり、各ドメインは複数のインスタンスを持つことができます。

OpenFrame環境設定でdsサブジェクトのDATASET_LOCKセクションのDBMS_LOCKキーのVALUE項目をYESに指定すると、ofrlhsvrサーバーを使用できます。""",
            "content_type": ContentType.API,
            "code_blocks": [
                'ofrlhsvr SVGNAME = svg_node1,',
                'CLOPT="-o $(SVR)$(DATE).out -e $(SVR)$(DATE).err"'
            ]
        },
        {
            "number": "A.6",
            "title": "ofrsasvr",
            "content": """ofrsasvrサーバーは、OpenFrameシステムのアクセス制御要求を受けて処理します。ユーザー制御サーバー(UCS)であり、各ドメインは1つのインスタンスを持ちます。""",
            "content_type": ContentType.API,
            "code_blocks": [
                'ofrsasvr SVGNAME = svg_domain, MIN = 1, MAX = 1, SVRTYPE=UCS,',
                'CLOPT="-o $(SVR)$(DATE).out -e $(SVR)$(DATE).err"'
            ]
        },
        {
            "number": "A.7",
            "title": "ofrsmlog",
            "content": """ofrsmlogサーバーはSMFレコードを記録し、SMFデータセットを管理します。Tmax制御サーバー(TCS)であり、各ドメインは1つのインスタンスを持ちます。""",
            "content_type": ContentType.API,
            "code_blocks": [
                'ofrsmlog SVGNAME = svg_domain, MIN = 1, MAX = 1,',
                'CLOPT="-o $(SVR)$(DATE).out -e $(SVR)$(DATE).err"'
            ]
        },
        {
            "number": "A.8",
            "title": "ofruisvr",
            "content": """ofruisvrサーバーはOFAdminやツールなどのクライアントからデータセットの作成および削除要求を受けて処理します。Tmax制御サーバー(TCS)であり、各ドメインは複数のインスタンスを持ちます。""",
            "content_type": ContentType.API,
            "code_blocks": [
                'ofruisvr SVGNAME = svg_node1,',
                'CLOPT="-o $(SVR)$(DATE).out -e $(SVR)$(DATE).err"'
            ]
        },
        {
            "number": "B.1",
            "title": "openframe_base.conf",
            "content": """OpenFrame/Baseシステムを運用するためには、openframe_base.confに以下のサブジェクトの各項目を設定した後、ofconfigツールを使用してOpenFrameシステムに設定を保存する必要があります。

主なサブジェクト：
● acs: ストレージ管理システムで使用されるSMSクラスの選択ルールを設定します。
● api3270: OpenFrameシステムで3270データ・ストリームの変換機能に関する一般的な設定を行います。
● console: OpenFrameシステムのコンソールとコマンドに関する設定を行います。
● cpm: OpenFrameシステムのコードページの変換に関する設定を行います。
● ds: OpenFrameシステムで使用されるデータセットの一般的な設定を行います。
● dstool: データセット関連のツール・プログラムで使用される設定を行います。
● ofsys: OpenFrameのシステム・ディレクトリ構造を含む全般的な設定を行います。
● saf: OpenFrameシステムのアクセス制御に関する設定を行います。
● smf: SMFで使用される設定を行います。
● sms: ストレージ管理システムで使用されるSMSクラスを定義します。
● sort: SORTユーティリティの一般的な設定を行います。""",
            "content_type": ContentType.CONFIGURATION
        },
        {
            "number": "B.2.1",
            "title": "[SYS1_ODBC]",
            "content": """OpenFrame/Baseシステムで使用するデータベース接続情報を設定するセクションです。

設定項目：
● DATABASE: 接続するデータベース名を指定します。
● USERNAME: データベースに接続するためのユーザー名を指定します。
● ENPASSWD: データベースに接続するための暗号化されたユーザー・パスワードを指定します。""",
            "content_type": ContentType.CONFIGURATION,
            "code_blocks": [
                "[SYS1_ODBC]",
                "DATABASE=tb_oframe7",
                "USERNAME=tibero",
                "ENPASSWD=AA68690384C8042F154AEDF2A7B9F2A52B27EB63AF0777D67076195863248D2A"
            ]
        },
        {
            "number": "C.2",
            "title": "システム表の作成",
            "content": """OpenFrameではシステム表を作成または削除するために、baseinitというツールを提供します。

baseinitツールが動作するためには、dbconn.confファイルの[SYS1_ODBC]セクションに設定されているDBCONN接続情報が必要です。""",
            "content_type": ContentType.PROCEDURE,
            "code_blocks": [
                "$ baseinit create -t DEFVOL"
            ]
        },
        {
            "number": "C.3",
            "title": "環境設定",
            "content": """OpenFrameではシステムの運用に必要な設定をTiberoの表に保存して管理します。

OpenFrameを使用するには、openframe_base.confファイルを必要に応じて修正し、ofconfigツールを使用して設定をTiberoの表に保存する必要があります。""",
            "content_type": ContentType.PROCEDURE,
            "code_blocks": [
                "$ ofconfig import -f openframe.conf -n NODE1"
            ]
        },
        {
            "number": "C.4",
            "title": "VSAMボリューム表領域の作成",
            "content": """OpenFrameではメインフレームのVSAMの機能と性能をサポートするために、下部ストレージ技術としてDBMSを利用したTSAMを提供します。内部的に、VSAMデータセットはDBMSの表に、VSAMデータセットが保存されるボリュームはDBMSの表領域にそれぞれマッピングされます。

非VSAMデータセットが作成されるUNIXディレクトリ・パスは、volmgrツールを使用して作成できます。""",
            "content_type": ContentType.PROCEDURE,
            "code_blocks": [
                'SQL> CREATE TABLESPACE "DEFVOL" DATAFILE \'DEFVOL.dbf\' SIZE 100M;'
            ]
        },
        {
            "number": "C.5",
            "title": "ボリュームの設定",
            "content": """メインフレームでは、システムの初期化時にシステム設定ファイルを編集することでストレージ・デバイスの設定を行います。OpenFrameでは、volmgrツールを使用してI/Oデバイスとシステム・ユニットの情報を設定します。

volmgrツールを使用してボリューム情報を設定すると、ボリューム・ディレクトリが自動的に生成されます。volmgrツールを実行するには、Tmaxエンジンを起動する必要があります。""",
            "content_type": ContentType.PROCEDURE,
            "code_blocks": [
                "$ volmgr define device -dn 0001 -dt 3380 -ms 2048 -dg SYSDA",
                "$ volmgr define volume -v DEFVOL -dn 0001"
            ]
        },
        {
            "number": "D.2",
            "title": "OpenFrameのログ",
            "content": """OpenFrameで生成されるログ・ファイルはそれぞれの特性によって、サービス・ログ、システム・ログ、操作ログ、データ・ログの4タイプに分類されます。

● サービス・ログ
Tmaxサーバーから作成され、OpenFrameエンジンによって出力されるメッセージを記録します。
ログ・ディレクトリ: ${TMAX_DIR}/log/ulog
ログ・ファイル名: $(SVR)$(DATE).out, $(SVR)$(DATE).err

● システム・ログ
OpenFrame内部で重要なイベントを記録します。
ログ・ディレクトリ: (LOG_DIR)/sys
ログ・ファイル名: ${MODULE_NAME}_YYYYMMDD.log

● 操作ログ
OpenFrameを運用するために、ユーザーがシェルまたはStudioを介して実行したコマンドを記録します。
ログ・ディレクトリ: (LOG_DIR)/cmd
ログ・ファイル名: ${MODULE_NAME}_YYYYMMDD.log

● データ・ログ
保存される内容がデータ形式で他の分析ツールの入力値として使用されます。
ログ・ディレクトリ: (LOG_DIR)/data
ログ・ファイル名: ${MODULE_NAME}_YYYYMMDD.log""",
            "content_type": ContentType.LOG
        },
        {
            "number": "D.2.1",
            "title": "サービス・ログ",
            "content": """Tmaxサーバーから作成され、OpenFrameエンジンによって出力されるメッセージを記録します。

ログ形式：
[YYYY-MM-DDTHH:MM:SS.ffffff] [SERVICE-NAME(PID)] [M] [MSGCODE] MESSAGE-CONTENTS

項目説明：
● [YYYY-MM-DDTHH:MM:SS.ffffff]: メッセージの出力時間です。
● SERVICE-NAME: 実行されたサービス名です。
● PID: サービスを実行したTmaxサーバーのPIDです。
● M: メッセージのタイプです。(M: Message, E: Error, W: Warning, D: Debug)
● MSGCODE: 8文字のメッセージ・コードです。""",
            "content_type": ContentType.LOG,
            "code_blocks": [
                '[2019-11-28T17:55:40.096148] [OFRUISVRPROFILE(15569)] [M] [SVR0100M] service starts.'
            ]
        },
        {
            "number": "D.3",
            "title": "OpenFrame/Baseシステムのログ",
            "content": """OpenFrame/Baseシステムでは、以下のようなログ・ファイルが生成されます。

サービス・ログ：
● ofrcmsvr$(DATE).out/err: ofrcmsvrサーバーのサービス・ログ
● ofrdmsvr$(DATE).out/err: ofrdmsvrサーバーのサービス・ログ
● ofrdsedt$(DATE).out/err: ofrdsedtサーバーのサービス・ログ
● ofrlhsvr$(DATE).out/err: ofrlhsvrサーバーのサービス・ログ
● ofruisvr$(DATE).out/err: ofruisvrサーバーのサービス・ログ
● ofrsmlog$(DATE).out/err: ofrsmlogサーバーのサービス・ログ
● ofrsasvr$(DATE).out/err: ofrsasvrサーバーのサービス・ログ

システム・ログ：
● ams_YYYYMMDD.log: カタログ管理のシステム・ログ
● dsalc_YYYYMMDD.log: データセット割り当てのシステム・ログ
● saf_YYYYMMDD.log: システム・セキュリティのシステム・ログ

操作ログ：
● dstool_YYYYMMDD.log: データセット管理の操作ログ

データ・ログ：
● console_YYYYMMDD.log: コンソール・メッセージのデータ・ログ""",
            "content_type": ContentType.LOG
        }
    ]
    
    # 질문 템플릿
    question_templates = {
        ContentType.DEFINITION: [
            "{title}とは何ですか？",
            "{title}について説明してください。"
        ],
        ContentType.COMMAND: [
            "{title}コマンドの使い方を教えてください。",
            "{title}の実行例を示してください。"
        ],
        ContentType.CONFIGURATION: [
            "{title}の設定方法を教えてください。",
            "{title}の設定例を示してください。"
        ],
        ContentType.PROCEDURE: [
            "{title}の手順を教えてください。",
            "{title}を実行する方法は？"
        ],
        ContentType.LOG: [
            "{title}について説明してください。",
            "{title}の形式と保存場所を教えてください。"
        ],
        ContentType.API: [
            "{title}サーバーの機能について説明してください。",
            "{title}の設定方法を教えてください。"
        ]
    }
    
    training_examples = []
    
    for section in sample_sections:
        templates = question_templates.get(
            section["content_type"],
            ["{title}について説明してください。"]
        )
        
        for template in templates:
            instruction = template.format(title=section["title"])
            
            output = section["content"]
            if section.get("code_blocks"):
                output += "\n\n使用例:\n"
                for code in section["code_blocks"]:
                    output += f"```\n{code}\n```\n"
            
            example = TrainingExample(
                instruction=instruction,
                input="",
                output=output,
                metadata={
                    "source": "OpenFrame Base Guide v7.1",
                    "section_number": section["number"],
                    "content_type": section["content_type"].value
                }
            )
            training_examples.append(example)
    
    # 메타데이터
    metadata = {
        "product": "OpenFrame/Base",
        "version": "7.1",
        "guide_version": "v3.1.2",
        "language": "ja",
        "total_sections": len(sample_sections),
        "total_examples": len(training_examples)
    }
    
    return training_examples, metadata


def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(
        description='OpenFrame 매뉴얼에서 QLoRA 학습 데이터 추출',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 샘플 데이터 생성
  python %(prog)s --sample --output training_data.jsonl

  # PDF에서 추출
  python %(prog)s --input manual.pdf --output data.jsonl --format alpaca

  # ShareGPT 형식으로 출력
  python %(prog)s --sample --format sharegpt --output data.jsonl
        """
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        help='입력 PDF 파일 경로'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='openframe_training_data.jsonl',
        help='출력 파일 경로 (기본: openframe_training_data.jsonl)'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['alpaca', 'sharegpt', 'openai', 'full'],
        default='alpaca',
        help='출력 형식 (기본: alpaca)'
    )
    parser.add_argument(
        '--language', '-l',
        choices=['ja', 'en'],
        default='ja',
        help='질문 언어 (기본: ja)'
    )
    parser.add_argument(
        '--sample',
        action='store_true',
        help='샘플 데이터 생성 모드 (PDF 없이 실행)'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='통계 정보만 출력'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("OpenFrame Base Guide QLoRA 학습 데이터 추출기")
    print("=" * 60)
    
    if args.sample or not args.input:
        print("\n[모드] 샘플 학습 데이터 생성")
        training_examples, doc_metadata = create_sample_training_data()
        
        # 출력
        output_path = args.output
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for example in training_examples:
                if args.format == 'alpaca':
                    data = example.to_alpaca_format()
                elif args.format == 'sharegpt':
                    data = example.to_sharegpt_format()
                elif args.format == 'openai':
                    data = example.to_openai_format()
                else:
                    data = example.to_dict()
                f.write(json.dumps(data, ensure_ascii=False) + '\n')
        
        print(f"\n✓ 생성 완료!")
        print(f"  총 학습 데이터: {len(training_examples)}개")
        print(f"  출력 파일: {output_path}")
        print(f"  출력 형식: {args.format}")
        
        # 통계
        print("\n[콘텐츠 유형별 통계]")
        type_counts = {}
        for ex in training_examples:
            ct = ex.metadata.get("content_type", "unknown")
            type_counts[ct] = type_counts.get(ct, 0) + 1
        
        for ct, count in sorted(type_counts.items()):
            print(f"  • {ct}: {count}개")
        
        # 샘플 출력
        print("\n[샘플 데이터 미리보기]")
        for i, ex in enumerate(training_examples[:2]):
            print(f"\n--- 예제 {i+1} ({ex.metadata['section_number']}) ---")
            print(f"Q: {ex.instruction}")
            print(f"A: {ex.output[:150]}...")
    
    else:
        # PDF 파싱 모드
        print(f"\n[모드] PDF 파싱")
        print(f"  입력 파일: {args.input}")
        
        if not Path(args.input).exists():
            print(f"Error: 파일을 찾을 수 없습니다: {args.input}")
            return
        
        manual_parser = OpenFrameManualParser()
        
        try:
            sections = manual_parser.parse_pdf(args.input)
        except ImportError as e:
            print(f"Error: {e}")
            return
        
        print(f"  파싱된 섹션 수: {len(sections)}")
        
        generator = QLoRADataGenerator(manual_parser)
        training_data = generator.generate_training_data(language=args.language)
        
        # Q&A 쌍 추가
        qa_pairs = generator.generate_qa_pairs(language=args.language)
        generator.training_data.extend(qa_pairs)
        
        # 출력
        if args.output.endswith('.json'):
            generator.export_json(args.output, args.format)
        else:
            generator.export_jsonl(args.output, args.format)
        
        # 통계 출력
        stats = generator.get_statistics()
        print("\n[통계]")
        print(f"  총 학습 예제: {stats['total_examples']}개")
        print(f"  총 섹션: {stats['total_sections']}개")
        print(f"  평균 질문 길이: {stats['avg_instruction_length']}자")
        print(f"  평균 응답 길이: {stats['avg_output_length']}자")
        print("\n[콘텐츠 유형별]")
        for ct, count in sorted(stats['by_content_type'].items()):
            print(f"  • {ct}: {count}개")
    
    print("\n" + "=" * 60)
    print("완료!")


if __name__ == "__main__":
    main()
