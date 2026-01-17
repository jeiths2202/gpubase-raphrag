#!/usr/bin/env python3
"""
Section-based Document Chunker
섹션 구조를 인식하여 문서를 청킹하는 모듈
"""
import re
import fitz
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class SectionChunk:
    """섹션 기반 청크"""
    chunk_id: str
    section_id: str          # e.g., "2.3.2"
    section_title: str       # e.g., "DEVステートメント"
    content: str
    page_numbers: List[int]
    chunk_index: int         # 섹션 내 청크 인덱스 (0이면 단일 청크)
    total_chunks: int        # 해당 섹션의 총 청크 수
    parent_section: Optional[str] = None  # 상위 섹션 ID


class SectionChunker:
    """섹션 기반 문서 청킹"""
    
    # 섹션 헤더 패턴 (일본어/한국어/영어 기술 문서)
    SECTION_PATTERNS = [
        r'^(\d+\.(?:\d+\.)*)\s*([^\n]+)',  # "2.3.2. Title" or "2.3.2 Title"
        r'^(第\d+章)\s*([^\n]+)',           # "第2章 Title" (Japanese)
        r'^(Chapter\s+\d+)\s*([^\n]+)',    # "Chapter 2 Title"
    ]
    
    def __init__(
        self,
        max_chunk_size: int = 1500,      # 섹션이 클 경우 분할 기준
        min_chunk_size: int = 200,       # 최소 청크 크기
        overlap_size: int = 100,         # 분할 시 오버랩
        embedding_token_limit: int = 450  # 임베딩 토큰 제한 (여유 포함)
    ):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap_size = overlap_size
        self.embedding_token_limit = embedding_token_limit
    
    def extract_text_with_pages(self, pdf_path: str) -> List[Tuple[int, str]]:
        """PDF에서 페이지별 텍스트 추출"""
        doc = fitz.open(pdf_path)
        pages = []
        for page_num, page in enumerate(doc, 1):
            text = page.get_text()
            if text.strip():
                pages.append((page_num, text))
        doc.close()
        return pages
    
    def find_sections(self, text: str) -> List[Tuple[int, str, str]]:
        """텍스트에서 섹션 헤더 찾기
        Returns: [(position, section_id, section_title), ...]
        """
        sections = []
        for pattern in self.SECTION_PATTERNS:
            for match in re.finditer(pattern, text, re.MULTILINE):
                section_id = match.group(1).strip().rstrip('.')
                section_title = match.group(2).strip()
                # 노이즈 필터링
                if len(section_title) > 2 and not any(x in section_title for x in ['...', '●', '>>-']):
                    sections.append((match.start(), section_id, section_title))
        
        # 위치 기준 정렬
        sections.sort(key=lambda x: x[0])
        return sections
    
    def get_parent_section(self, section_id: str) -> Optional[str]:
        """상위 섹션 ID 반환 (예: 2.3.2 -> 2.3)"""
        parts = section_id.split('.')
        if len(parts) > 1:
            return '.'.join(parts[:-1])
        return None
    
    def split_large_section(
        self, 
        content: str, 
        section_id: str, 
        section_title: str
    ) -> List[str]:
        """큰 섹션을 작은 청크로 분할 (섹션 제목 포함)"""
        # 섹션 헤더를 각 청크에 추가
        header = f"[{section_id}. {section_title}]\n\n"
        header_len = len(header)
        available_size = self.max_chunk_size - header_len
        
        chunks = []
        start = 0
        
        while start < len(content):
            end = min(start + available_size, len(content))
            
            # 문장/단락 경계에서 분할 시도
            if end < len(content):
                # 마지막 마침표, 줄바꿈 찾기
                last_break = max(
                    content.rfind('。', start, end),
                    content.rfind('.', start, end),
                    content.rfind('\n\n', start, end),
                    content.rfind('\n', start, end)
                )
                if last_break > start + available_size * 0.5:
                    end = last_break + 1
            
            chunk_content = content[start:end].strip()
            if chunk_content:
                chunks.append(header + chunk_content)
            
            start = end - self.overlap_size if end < len(content) else len(content)
        
        return chunks if chunks else [header + content]
    
    def chunk_document(
        self, 
        pdf_path: str, 
        doc_id: str
    ) -> List[SectionChunk]:
        """문서를 섹션 기반으로 청킹"""
        # 전체 텍스트 추출 (페이지 정보 포함)
        pages = self.extract_text_with_pages(pdf_path)
        full_text = "\n".join([text for _, text in pages])
        
        # 섹션 찾기
        sections = self.find_sections(full_text)
        
        if not sections:
            # 섹션이 없으면 고정 크기 청킹으로 폴백
            return self._fallback_chunking(full_text, doc_id)
        
        chunks = []
        chunk_counter = 0
        
        for i, (pos, section_id, section_title) in enumerate(sections):
            # 다음 섹션 시작 위치
            next_pos = sections[i + 1][0] if i + 1 < len(sections) else len(full_text)
            
            # 섹션 내용 추출
            section_content = full_text[pos:next_pos].strip()
            
            # 섹션 제목 라인 제거 (이미 메타데이터로 저장)
            content_lines = section_content.split('\n')
            if content_lines:
                # 첫 줄이 섹션 제목이면 제거
                if section_id in content_lines[0]:
                    content_lines = content_lines[1:]
            section_content = '\n'.join(content_lines).strip()
            
            if len(section_content) < self.min_chunk_size:
                continue
            
            # 페이지 번호 추출
            page_nums = self._find_page_numbers(section_content, pages)
            
            # 섹션 크기 체크
            if len(section_content) <= self.max_chunk_size:
                # 단일 청크
                header = f"[{section_id}. {section_title}]\n\n"
                chunks.append(SectionChunk(
                    chunk_id=f"chunk_{doc_id}_{chunk_counter:04d}",
                    section_id=section_id,
                    section_title=section_title,
                    content=header + section_content,
                    page_numbers=page_nums,
                    chunk_index=0,
                    total_chunks=1,
                    parent_section=self.get_parent_section(section_id)
                ))
                chunk_counter += 1
            else:
                # 큰 섹션 분할
                sub_chunks = self.split_large_section(
                    section_content, section_id, section_title
                )
                for j, sub_content in enumerate(sub_chunks):
                    chunks.append(SectionChunk(
                        chunk_id=f"chunk_{doc_id}_{chunk_counter:04d}",
                        section_id=section_id,
                        section_title=section_title,
                        content=sub_content,
                        page_numbers=page_nums,
                        chunk_index=j,
                        total_chunks=len(sub_chunks),
                        parent_section=self.get_parent_section(section_id)
                    ))
                    chunk_counter += 1
        
        return chunks
    
    def _find_page_numbers(
        self, 
        content: str, 
        pages: List[Tuple[int, str]]
    ) -> List[int]:
        """콘텐츠가 포함된 페이지 번호 찾기"""
        page_nums = []
        content_sample = content[:200]  # 시작 부분으로 매칭
        
        for page_num, page_text in pages:
            if content_sample[:50] in page_text:
                page_nums.append(page_num)
                # 연속 페이지 체크
                for next_page_num, next_page_text in pages:
                    if next_page_num > page_num and content[-100:] in next_page_text:
                        page_nums.append(next_page_num)
                        break
                break
        
        return page_nums if page_nums else [1]
    
    def _fallback_chunking(
        self, 
        text: str, 
        doc_id: str
    ) -> List[SectionChunk]:
        """섹션이 없는 경우 고정 크기 청킹"""
        chunks = []
        start = 0
        chunk_counter = 0
        
        while start < len(text):
            end = min(start + self.max_chunk_size, len(text))
            if end < len(text):
                last_break = text.rfind('\n', start, end)
                if last_break > start + self.max_chunk_size * 0.5:
                    end = last_break
            
            chunk_content = text[start:end].strip()
            if chunk_content and len(chunk_content) >= self.min_chunk_size:
                chunks.append(SectionChunk(
                    chunk_id=f"chunk_{doc_id}_{chunk_counter:04d}",
                    section_id="",
                    section_title="",
                    content=chunk_content,
                    page_numbers=[1],
                    chunk_index=chunk_counter,
                    total_chunks=0,
                    parent_section=None
                ))
                chunk_counter += 1
            
            start = end - self.overlap_size if end < len(text) else len(text)
        
        return chunks


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python section_chunker.py <pdf_path> [doc_id]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    doc_id = sys.argv[2] if len(sys.argv) > 2 else "test_doc"
    
    chunker = SectionChunker(max_chunk_size=1200)
    chunks = chunker.chunk_document(pdf_path, doc_id)
    
    print(f"\n=== Chunking Results ===")
    print(f"Total chunks: {len(chunks)}")
    
    for chunk in chunks[:10]:
        print(f"\n--- {chunk.chunk_id} ---")
        print(f"Section: {chunk.section_id}. {chunk.section_title}")
        print(f"Pages: {chunk.page_numbers}")
        print(f"Part: {chunk.chunk_index + 1}/{chunk.total_chunks}")
        print(f"Size: {len(chunk.content)} chars")
        print(f"Preview: {chunk.content[:200]}...")
